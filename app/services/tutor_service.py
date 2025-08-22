import json
import logging
import time
import hashlib
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession, joinedload

from app.config import settings
from app.database import get_db  # assume you have a standard get_db() dependency
from app.utils.helper import clean_json_response
from app.utils.error_handling import retry_on_exception, RetryableError
from app.utils.template import ( TUTOR_SYSTEM_PROMPT, TUTOR_USER_PROMPT_TEMPLATE )

from app.models import (
    Question,
    Flashcard,
    Document,
    DocumentChunk,
    Session as SessionModel,
)
from app.processors.vector_processor import vector_processor
from openai import OpenAI
from app.processors.tutor_agent import TutorAgent
from app.schemas.tutor import (
    TutorChatRequest,
    TutorChatResponse,
    TutorExplainResponse
)

logger = logging.getLogger(__name__)

class TutorService:
    def __init__(self):
        self.agent = TutorAgent()
        self.vector = vector_processor

    # ---- public API ----
    def explain_question(self, db: OrmSession, question_id: str, user_message: str, top_k: int = 6) -> TutorExplainResponse:
        q: Optional[Question] = (
            db.query(Question)
            .options(joinedload(Question.question_answers))
            .filter(Question.id == question_id)
            .first()
        )
        if not q:
            raise HTTPException(status_code=404, detail="Question not found")

        session_id = q.session_id
        topic = q.topic or "General"
        item_text = q.content
        item_type = q.type or "multiple_choice"
        doc_ids = [d.id for d in db.query(Document).filter(Document.session_id == session_id).all()]

        ctx_pack = self._build_context(db, topic, item_text, user_message, doc_ids, top_k)
        reply, citations = self._chat_once(topic, item_type, item_text, user_message, ctx_pack)

        return TutorExplainResponse(
            question_id=question_id,
            reply=reply,
            citations=citations,
            used_context=ctx_pack["sources_block"],
            next_suggestions=ctx_pack["next_suggestions"],
        )

    def chat(self, db: OrmSession, req: TutorChatRequest) -> TutorChatResponse:
        # Identify base prompt item
        item_text = ""
        item_type = "chat"
        topic = "General"

        if req.question_id:
            q: Optional[Question] = db.query(Question).filter(Question.id == req.question_id).first()
            if not q:
                raise HTTPException(status_code=404, detail="Question not found")
            item_text = q.content
            item_type = q.type or "question"
            topic = q.topic or topic
        elif req.flashcard_id:
            f: Optional[Flashcard] = db.query(Flashcard).filter(Flashcard.id == req.flashcard_id).first()
            if not f:
                raise HTTPException(status_code=404, detail="Flashcard not found")
            item_text = f.question
            item_type = f.card_type or "flashcard"
            topic = f.topic or topic
        else:
            # Pure chat within a session/topic
            # try to infer topic from recent questions in the session
            recent_q = (
                db.query(Question)
                .filter(Question.session_id == req.session_id)
                .order_by(Question.created_at.desc())
                .first()
            )
            if recent_q:
                topic = recent_q.topic or topic

        # documents to consider
        if req.document_ids:
            doc_ids = req.document_ids
        else:
            doc_ids = [d.id for d in db.query(Document).filter(Document.session_id == req.session_id).all()]

        user_message = self._build_user_message(req)
        ctx_pack = self._build_context(db, topic, item_text, user_message, doc_ids, req.top_k)
        reply, citations = self._chat_once(topic, item_type, item_text, user_message, ctx_pack)

        return TutorChatResponse(
            reply=reply,
            citations=citations,
            used_context=ctx_pack["sources_block"],
            next_suggestions=ctx_pack["next_suggestions"],
        )

    # ---- internals ----
    def _build_user_message(self, req: TutorChatRequest) -> str:
        pieces: List[str] = []
        if req.history:
            # keep a compact summary of the last few messages
            last = req.history[-6:]
            for turn in last:
                pieces.append(f"{turn.role}: {turn.content}")
        pieces.append(f"user: {req.message}")
        if req.response_style:
            pieces.append(f"[style preference: {req.response_style}]")
        return "\n".join(pieces)

    def _build_context(
        self,
        db: OrmSession,
        topic: str,
        item_text: str,
        user_message: str,
        document_ids: List[str],
        top_k: int,
    ) -> Dict[str, Any]:
        # Compose a retrieval query blending the item and the current message
        retrieval_query = (item_text or "") + "\n" + (user_message or "")
        results = self.vector.similarity_search(db, retrieval_query, document_ids=document_ids, top_k=top_k)

        # Build sources block
        sources_lines: List[str] = []
        citations: List[Dict[str, str]] = []
        for idx, r in enumerate(results, start=1):
            tag = f"S{idx}"
            # fetch filename for more meaningful citation
            doc = db.query(Document).filter(Document.id == r["document_id"]).first()
            filename = doc.filename if doc else r["document_id"]
            content = (r["content"] or "").strip().replace("\n", " ")
            # Clip long chunks to keep prompts efficient
            if len(content) > 750:
                content = content[:750] + " …"
            sources_lines.append(f"[{tag}] (doc: {filename})\n{content}")
            citations.append({"tag": f"[{tag}]", "doc_id": r["document_id"], "filename": filename})

        if not sources_lines:
            sources_lines.append("[S1] No relevant context found.")

        sources_block = "\n\n".join(sources_lines)

        # Provide a couple of default next suggestions; model may augment
        next_suggestions = [
            "Try a similar practice question.",
            "Ask for a step-by-step outline of the solution approach.",
        ]

        return {
            "sources_block": sources_block,
            "citations": citations,
            "next_suggestions": next_suggestions,
        }

    def _chat_once(
        self,
        topic: str,
        item_type: str,
        item_text: str,
        user_message: str,
        ctx_pack: Dict[str, Any],
    ) -> (str, List[Dict[str, str]]):
        user_prompt = TUTOR_USER_PROMPT_TEMPLATE.format(
            topic=topic,
            item_type=item_type,
            item_text=item_text or "(no base item)",
            message=user_message,
            sources_block=ctx_pack["sources_block"],
        )
        raw = self.agent._complete(TUTOR_SYSTEM_PROMPT, user_prompt, max_tokens=1200)
        cleaned = clean_json_response(raw)
        try:
            data = json.loads(cleaned)
        except Exception as e:
            logger.warning(f"JSON parsing failed; returning raw text. Error: {e}")
            # Fallback shape
            return cleaned, ctx_pack["citations"]

        reply = data.get("reply") or "(No reply)"
        # if model produced its own citations block, prefer it but validate tags
        model_citations = data.get("citations") or []
        valid_tags = {c["tag"] for c in ctx_pack["citations"]}
        filtered = []
        for c in model_citations:
            try:
                tag = c.get("tag")
                if tag in valid_tags:
                    # merge filename/doc_id from our records for consistency
                    base = next(x for x in ctx_pack["citations"] if x["tag"] == tag)
                    filtered.append(base)
            except Exception:
                continue
        if not filtered:
            filtered = ctx_pack["citations"]

        # allow the model to include next suggestions; otherwise keep defaults
        if data.get("next_suggestions"):
            ctx_pack["next_suggestions"] = data["next_suggestions"]

        return reply, filtered

tutor_service = TutorService()