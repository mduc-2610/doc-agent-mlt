import uuid
import logging
from sqlalchemy.orm import Session
from fastapi import HTTPException
from typing import Dict, Any
from app.models import Question, QuestionAnswer, Flashcard
from app.config import current_date_time, settings
from app.processors.content_generator import content_generator
from app.schemas.question import QuestionGenerationRequest
from app.schemas.message import MessageResponse
from app.processors.vector_processor import vector_processor
from app.utils.template import (
    RAG_QUESTION_PROMPT_TEMPLATE, 
    RAG_FLASHCARD_PROMPT_TEMPLATE
)

logger = logging.getLogger(__name__)

class QuestionGenerationService:
    def __init__(self):
        self.content_generator = content_generator
        self.vector_processor = vector_processor

    def process_rag_quiz_and_flashcards(self, request: QuestionGenerationRequest, db: Session) -> Dict[str, Any]:
        try:
            context = self.vector_processor.get_relevant_context(
                db, request.topic, request.document_ids, max_context_length=settings.rag.max_context_length
            )
            
            if not context.strip():
                raise HTTPException(
                    status_code=400, 
                    detail=MessageResponse.create(
                        translation_key="noRelevantContext",
                        message="No relevant context found"
                    ).model_dump()
                )
            
            questions_count = flashcards_count = 0
            warnings = []
            
            if request.quiz_count > 0:
                questions_count = self._generate_questions(request, context, db)
                if questions_count < request.quiz_count:
                    missing = request.quiz_count - questions_count
                    warnings.append(f"Could only generate {questions_count}/{request.quiz_count} questions ({missing} failed)")
            
            if request.flashcard_count > 0:
                flashcards_count = self._generate_flashcards(request, context, db)
                if flashcards_count < request.flashcard_count:
                    missing = request.flashcard_count - flashcards_count
                    warnings.append(f"Could only generate {flashcards_count}/{request.flashcard_count} flashcards ({missing} failed)")
            
            total_requested = request.quiz_count + request.flashcard_count
            total_generated = questions_count + flashcards_count
            success_rate = (total_generated / total_requested * 100) if total_requested > 0 else 100
            
            status = "success" if success_rate >= 90 else "partial_success" if success_rate >= 50 else "warning"
            
            response = {
                "status": status,
                "message": "Questions and flashcards generated successfully" if status == "success" else "Partial generation completed",
                "questions_generated": questions_count,
                "flashcards_generated": flashcards_count,
                "success_rate": round(success_rate, 1),
                "context_length": len(context)
            }
            
            if warnings:
                response["warnings"] = warnings
            
            return response

        except Exception as e:
            logger.error(f"Question generation failed: {e}")
            raise HTTPException(
                status_code=500, 
                detail=MessageResponse.create(
                    translation_key="generationFailed",
                    message="Question generation failed"
                ).model_dump()
            )
    
    def _generate_questions(self, request: QuestionGenerationRequest, context: str, db: Session) -> int:      
        items = self.content_generator.generate_questions_chunked(
            RAG_QUESTION_PROMPT_TEMPLATE, request.topic, context, request.quiz_count
        )
        
        total_saved = 0
        for item in items:
            try:
                question_id = str(uuid.uuid4())
                question = Question(
                    id=question_id,
                    content=item["question"],
                    type=item.get("type", "multiple_choice"),
                    difficulty_level=item.get("difficulty_level", "medium"),
                    correct_answer=item["correct_answer"],
                    explanation=item.get("explanation", "Generated from context"),
                    topic=request.topic,
                    source_context=context[:300],
                    generation_model=self.content_generator.model_name,
                    session_id=request.session_id,
                    created_at=current_date_time()
                )
                db.add(question)
                db.flush()
                
                for opt in item["options"]:
                    answer = QuestionAnswer(
                        id=str(uuid.uuid4()),
                        content=opt,
                        is_correct=(opt == item["correct_answer"]),
                        explanation="",
                        question_id=question_id
                    )
                    db.add(answer)
                
                total_saved += 1
            except Exception as e:
                logger.debug(f"Skipped invalid question: {e}")
                continue
        
        db.commit()
        return total_saved
    
    def _generate_flashcards(self, request: QuestionGenerationRequest, context: str, db: Session) -> int:      
        items = self.content_generator.generate_flashcards_chunked(
            RAG_FLASHCARD_PROMPT_TEMPLATE, request.topic, context, request.flashcard_count
        )
        
        total_saved = 0
        for item in items:
            try:
                flashcard = Flashcard(
                    id=str(uuid.uuid4()),
                    card_type=item.get("type", "concept_flashcard"),
                    question=item["question"],
                    answer=item["answer"],
                    explanation=item.get("explanation", ""),
                    topic=request.topic,
                    source_context=context[:300],
                    generation_model=self.content_generator.model_name,
                    session_id=request.session_id,
                    created_at=current_date_time()
                )
                db.add(flashcard)
                total_saved += 1
            except Exception as e:
                logger.debug(f"Skipped invalid flashcard: {e}")
                continue
        
        db.commit()
        return total_saved

question_gen_service = QuestionGenerationService()
