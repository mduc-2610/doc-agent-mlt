import time
import hashlib
import logging
from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session
from openai import OpenAI
from fastapi import HTTPException

from app.config import settings
from app.models import Document
from app.processors.vector_processor import vector_processor
from app.utils.helper import clean_json_response

logger = logging.getLogger(__name__)

class ExplainService:
    def __init__(self):
        # Dùng DeepSeek via OpenRouter (giống question_generator)
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openai_api_key,
        )
        self.model_name = "deepseek/deepseek-r1-0528:free"
        self.timeout = settings.rag.generation_timeout
        self.max_retries = getattr(settings.rag, "max_retries", 3)
        self.cache = {}

    # -------- Retrieval helpers --------
    def _session_document_ids(self, db: Session, session_id: str) -> List[str]:
        return [d.id for d in db.query(Document).filter(Document.session_id == session_id).all()]

    def _multi_query(self, stem: str, options: Optional[List[str]]) -> List[str]:
        qs = [stem]
        if options:
            for opt in options:
                qs.append(f"{stem}\nOption: {opt}")
        if len(stem) > 20:
            # paraphrase nhẹ nhàng
            qs.append(stem.replace(" là gì", " định nghĩa"))
        return qs

    def _fused_hits(
        self, db: Session, doc_ids: List[str], queries: List[str], top_k_each: int
    ) -> List[Dict[str, Any]]:
        seen, fused = set(), []
        for qi, q in enumerate(queries):
            hits = vector_processor.similarity_search(db, q, doc_ids, top_k=top_k_each)
            for rank, h in enumerate(hits):
                key = (h["document_id"], h["chunk_index"])
                if key in seen:
                    continue
                seen.add(key)
                # RRF + nhẹ boost nếu đến từ truy vấn option-aware
                score = h["similarity_score"] + 1.0 / (60 + rank) + (0.05 if qi > 0 else 0.0)
                fused.append({**h, "score": score, "q_idx": qi})
        fused.sort(key=lambda x: x["score"], reverse=True)
        return fused

    def _pack_per_option(self, fused: List[Dict[str, Any]], options: List[str]) -> Dict[str, List[Dict]]:
        per = {}
        for opt in options:
            bucket = []
            opt_low = opt.lower()
            opt_tokens = opt_low.split()[:2]  # match lỏng
            for h in fused:
                if len(bucket) >= 3:
                    break
                text = h["content"].lower()
                if any(tok in text for tok in opt_tokens):
                    bucket.append(h)
            per[opt] = bucket
        return per

    def _build_context(self, items: List[Dict[str, Any]], max_chars: int = 1800) -> str:
        out, used = [], 0
        for x in items:
            snippet = x["content"].strip()
            tag = f"[{x['document_id']}:{x['chunk_index']}]"
            block = f"{snippet}\n{tag}"
            if used + len(block) > max_chars:
                break
            out.append(block)
            used += len(block)
        return "\n\n---\n\n".join(out)

    # -------- LLM call (DeepSeek) --------
    def _hash(self, s: str) -> str:
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    def _call_deepseek(self, prompt: str, max_tokens: int = 1400) -> str:
        key = self._hash(prompt)
        if key in self.cache:
            return self.cache[key]

        last_err = None
        for attempt in range(self.max_retries):
            try:
                completion = self.client.chat.completions.create(
                    extra_headers={
                        "HTTP-Referer": "https://openrouter.ai/deepseek/deepseek-r1-0528:free",
                        "X-Title": "DeepSeek: R1 0528 (free)",
                    },
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    timeout=self.timeout,
                )
                text = completion.choices[0].message.content
                # cache nhẹ
                if len(self.cache) < 1000:
                    self.cache[key] = text
                return text
            except Exception as e:
                last_err = e
                logger.warning(f"DeepSeek call failed (attempt {attempt+1}): {e}")
                time.sleep(1.5 * (2 ** attempt))
        raise HTTPException(status_code=502, detail=f"DeepSeek error: {last_err}")

    # -------- Public API --------
    def explain(
        self,
        db: Session,
        session_id: str,
        stem: str,
        options: Optional[List[str]] = None,
        top_k_each: int = 8,
    ) -> Dict[str, Any]:
        if not stem or not stem.strip():
            raise HTTPException(status_code=400, detail="stem is empty")

        doc_ids = self._session_document_ids(db, session_id)
        print(f"Session {session_id} has {len(doc_ids)} documents")
        if not doc_ids:
            return {
                "mode": "method_only",
                "message": "Không tìm thấy tài liệu trong session để trích dẫn.",
            }

        queries = self._multi_query(stem, options)
        fused = self._fused_hits(db, doc_ids, queries, top_k_each=top_k_each)

        # evidence
        global_top = fused[:6]
        combined = global_top
        if options:
            per_option = self._pack_per_option(fused, options)
            combined = []
            for opt in options:
                combined += per_option.get(opt, [])[:2]
            if not combined:
                combined = global_top

        context = self._build_context(combined) if combined else ""
        if not context:
            return {
                "mode": "method_only",
                "message": "Không tìm được trích dẫn phù hợp; vui lòng cung cấp thêm ngữ cảnh.",
            }

        # Prompt chỉ cho JSON, cấm chain-of-thought
        schema_hint = """
Xuất đúng JSON (không tiền tố/hậu tố, không giải thích), schema:
{
  "answer_choice": "<một trong các option, ví dụ: A/B/C/D hoặc chuỗi khớp nguyên văn>",
  "explanation_bullets": ["...", "..."],     // 2-6 gạch đầu dòng, mỗi dòng có [citation]
  "why_not": {"A": "...", "B": "...", "...": "..."},  // 1 dòng/option, có [citation] nếu có
  "citations": ["docId:chunkIdx", "..."],    // danh sách citation bạn đã dùng
  "confidence": 0.0                          // 0..1
}
KHÔNG đưa chain-of-thought, KHÔNG văn bản ngoài JSON.
"""
        opts_text = "\n".join([f"- {o}" for o in options]) if options else "(Không có phương án)"

        prompt = f"""
Bạn là trợ lý giải thích đáp án dựa hoàn toàn vào trích dẫn sau. 
Chỉ trình bày kết luận ngắn gọn (bullet), mọi khẳng định cần [citation] tương ứng.

ĐỀ BÀI:
{stem}

CÁC PHƯƠNG ÁN:
{opts_text}

NGỮ CẢNH (trích dẫn):
{context}

{schema_hint}
"""

        raw = self._call_deepseek(prompt)
        cleaned = clean_json_response(raw)

        import json
        try:
            data = json.loads(cleaned)
        except Exception as e:
            logger.warning(f"JSON parse failed, returning text fallback. Raw len={len(raw)} err={e}")
            return {
                "mode": "text_fallback",
                "raw": raw,
                "note": "DeepSeek không trả JSON hợp lệ; xem 'raw'.",
            }

        # chuẩn hóa trường
        data.setdefault("answer_choice", "")
        data.setdefault("explanation_bullets", [])
        data.setdefault("why_not", {})
        data.setdefault("citations", [])
        data.setdefault("confidence", 0.0)

        # nếu thiếu citation, hạ confidence
        if not data["citations"]:
            data["confidence"] = min(data["confidence"], 0.4)

        return {"mode": "ok", "result": data}

explain_service = ExplainService()
