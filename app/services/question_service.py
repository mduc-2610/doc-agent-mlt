import uuid
import traceback
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException
from typing import Dict, Any
from app.models import Question, QuestionAnswer, Flashcard, QuestionGeneration
import logging
from app.config import current_date_time
from app.processors.question_generator import question_generator
from app.schemas.question import (
    DocumentGenerationRequest,
    DocumentFileUploadRequest,
    DocumentUrlUploadRequest,
)
from app.processors.content_processor import content_processor
from app.utils.helper import detect_url_type, detect_file_type
from app.services.vector_service import vector_service

logger = logging.getLogger(__name__)

class QuestionService:
    def __init__(self):
        self.question_generator = question_generator
        self.content_processor = content_processor
        self.vector_service = vector_service

    def get_questions_by_document(self, db: Session, document_id: str):
        return (
            db.query(Question)
            .options(joinedload(Question.question_answers))
            .filter(Question.document_id == document_id)
            .all()
        )

    def get_flashcards_by_document(self, db: Session, document_id: str):
        return db.query(Flashcard).filter(Flashcard.document_id == document_id).all()

    def delete_questions_by_document(self, db: Session, document_id: str):
        db.query(Question).filter(Question.document_id == document_id).delete()
        db.commit()

    def delete_flashcards_by_document(self, db: Session, document_id: str):
        db.query(Flashcard).filter(Flashcard.document_id == document_id).delete()
        db.commit()
    
    def process_rag_quiz_and_flashcards(self, topic: str, document_ids: list, session_id: str, user_id: str, quiz_count: int, flashcard_count: int, db: Session) -> Dict[str, Any]:
        try:
            relevant_context = self.vector_service.get_relevant_context(
                db, topic, document_ids, max_context_length=4000
            )
            if not relevant_context.strip():
                raise HTTPException(status_code=400, detail="No relevant context found for the given topic")

            generation_record = QuestionGeneration(
                user_input=f"Topic: {topic}",
                context_chunks=[{"content": relevant_context, "source": "vector_search"}],
                generation_parameters={
                    "quiz_count": quiz_count,
                    "flashcard_count": flashcard_count,
                    "model": self.question_generator.model_name,
                    "document_ids": document_ids,
                },
                model_version=self.question_generator.model_name,
                generation_status="processing",
            )
            db.add(generation_record)
            db.flush()

            quiz_questions = self.question_generator.generate_rag_quiz(topic, relevant_context, quiz_count)
            flashcards = self.question_generator.generate_rag_flashcards(topic, relevant_context, flashcard_count)

            for q in quiz_questions:
                quality_score = self.question_generator.calculate_quality_score(
                    {"question": q.question, "answer": q.correct_answer, "explanation": q.explanation}, relevant_context
                )
                question_obj = Question(
                    content=q.question,
                    type=q.type,
                    difficulty_level=q.difficulty_level,
                    topic=q.topic,
                    correct_answer=q.correct_answer,
                    document_id=document_ids[0] if document_ids else None,
                    session_id=session_id,
                    user_id=user_id,
                    explanation=q.explanation,
                    source_context=q.source_context,
                    generation_model=self.question_generator.model_name,
                    validation_score=quality_score,
                    created_at=current_date_time(),
                )
                db.add(question_obj)
                db.flush()

                for ans in q.answers:
                    db.add(
                        QuestionAnswer(
                            content=ans.content,
                            is_correct=ans.is_correct,
                            explanation=ans.explanation,
                            question_id=question_obj.id,
                        )
                    )

            for f in flashcards:
                quality_score = self.question_generator.calculate_quality_score(
                    {"question": f.question, "answer": f.answer, "explanation": f.explanation}, relevant_context
                )
                flashcard_obj = Flashcard(
                    card_type=f.card_type,
                    question=f.question,
                    answer=f.answer,
                    explanation=f.explanation,
                    topic=f.topic,
                    source_context=f.source_context,
                    generation_model=self.question_generator.model_name,
                    validation_score=quality_score,
                    document_id=document_ids[0] if document_ids else None,
                    session_id=session_id,
                    user_id=user_id,
                    created_at=current_date_time(),
                )
                db.add(flashcard_obj)

            generation_record.output_questions = [
                {"type": "quiz", "count": len(quiz_questions)},
                {"type": "flashcard", "count": len(flashcards)},
            ]
            generation_record.final_questions = generation_record.output_questions
            generation_record.generation_status = "completed"
            generation_record.updated_at = current_date_time()

            db.commit()

            return {
                "generation_id": str(generation_record.id),
                "topic": topic,
                "document_ids": document_ids,
                "session_id": session_id,
                "quiz_questions": quiz_questions,
                "flashcards": flashcards,
                "context_used": relevant_context[:200] + "..." if len(relevant_context) > 200 else relevant_context,
                "created_at": current_date_time(),
            }

        except Exception as e:
            db.rollback()
            if "generation_record" in locals():
                generation_record.generation_status = "failed"
                generation_record.updated_at = current_date_time()
                db.commit()
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))

    def generate_question_from_url_service(self, request: DocumentUrlUploadRequest, db: Session):
        try:
            from app.services.document_service import document_service
            
            url_type = detect_url_type(request.url)
            if url_type == "youtube":
                document = document_service.parse_youtube(db, request.url, request.session_id)
            else:
                document = document_service.parse_web_url(db, request.url, request.session_id)

            document_id = str(document.id)
            with open(document.content_file_path, "r", encoding="utf-8") as f:
                text_content = f.read()

            self.vector_service.chunk_and_embed_document(db, document_id, text_content)

            return self.process_rag_quiz_and_flashcards(
                topic="General content analysis",
                document_ids=[document_id],
                session_id=str(document.session_id) if document.session_id else None,
                user_id=request.user_id,
                quiz_count=request.question_count,
                flashcard_count=request.flashcard_count,
                db=db,
            )
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))

    def generate_question_from_file_service(self, request: DocumentFileUploadRequest, db: Session):
        try:
            from app.services.document_service import document_service
            
            file_type = detect_file_type(request.file)
            if file_type == "audio_video":
                document = document_service.parse_audio_video(db, request.file, request.session_id)
            else:
                document = document_service.parse_document(db, request.file, request.session_id)

            document_id = str(document.id)
            with open(document.content_file_path, "r", encoding="utf-8") as f:
                text_content = f.read()

            self.vector_service.chunk_and_embed_document(db, document_id, text_content)

            return self.process_rag_quiz_and_flashcards(
                topic="General content analysis",
                document_ids=[document_id],
                session_id=str(document.session_id) if document.session_id else None,
                user_id=request.user_id,
                quiz_count=request.question_count,
                flashcard_count=request.flashcard_count,
                db=db,
            )
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))

question_service = QuestionService()