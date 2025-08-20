import uuid
import traceback
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException
from typing import Dict, Any
from app.models import Question, QuestionAnswer, Flashcard
import logging
from app.config import current_date_time
from app.processors.question_generator import question_generator
from app.schemas.question import (
    QuestionGenerationRequest,
    DocumentFileUploadRequest,
    DocumentUrlUploadRequest,
)
from app.processors.content_processor import content_processor
from app.utils.helper import detect_url_type, detect_file_type
from app.services.vector_service import VectorService
from app.services.document_service import document_service
from app.services.summary_service import summary_service
from app.schemas.document import FileParseRequest, UrlParseRequest
from app.utils.error_handling import (
    handle_database_errors, 
    handle_llm_errors, 
    validate_input,
    validate_question_generation_request,
    ErrorCollector,
    safe_execute
)
from app.services.monitoring_service import monitoring_service, MonitoredOperation
from app.database import BatchOperations

logger = logging.getLogger(__name__)

class QuestionService:
    def __init__(self):
        self.question_generator = question_generator
        self.content_processor = content_processor
        self.vector_service = VectorService()

    @handle_database_errors
    def get_questions_by_session(self, db: Session, session_id: str):
        with MonitoredOperation("get_questions_by_session") as op:
            op.add_metadata(session_id=session_id)
            
            questions = (
                db.query(Question)
                .options(joinedload(Question.question_answers))
                .filter(Question.session_id == session_id)
                .all()
            )
            
            op.add_metadata(questions_found=len(questions))
            return questions
    

    @handle_database_errors
    def get_flashcards_by_session(self, db: Session, session_id: str):
        with MonitoredOperation("get_flashcards_by_session") as op:
            op.add_metadata(session_id=session_id)
            
            flashcards = db.query(Flashcard).filter(Flashcard.session_id == session_id).all()
            
            op.add_metadata(flashcards_found=len(flashcards))
            return flashcards

    @handle_database_errors
    @handle_llm_errors
    # @validate_input(validate_question_generation_request)
    def process_rag_quiz_and_flashcards(self, request: QuestionGenerationRequest, db: Session) -> Dict[str, Any]:
        """ processing with comprehensive error handling and monitoring"""
        with MonitoredOperation("process_rag_quiz_and_flashcards") as op:
            try:
                op.add_metadata(
                    topic=request.topic,
                    document_count=len(request.document_ids),
                    quiz_count=request.quiz_count,
                    flashcard_count=request.flashcard_count
                )
                
                relevant_context = self.vector_service.get_relevant_context(
                    db, request.topic, request.document_ids, max_context_length=4000
                )
                
                if not relevant_context.strip():
                    raise HTTPException(status_code=400, detail="No relevant context found for the given topic")

                op.add_metadata(context_length=len(relevant_context))
                
                questions = self.question_generator.generate_rag_quiz(
                    request.topic, relevant_context, request.quiz_count
                )
                flashcards = self.question_generator.generate_rag_flashcards(
                    request.topic, relevant_context, request.flashcard_count
                )
                
                op.add_metadata(
                    questions_generated=len(questions),
                    flashcards_generated=len(flashcards)
                )
                
                questions_data = []
                flashcards_data = []
                question_answers_data = []
                
                error_collector = ErrorCollector()
                
                for q in questions:
                    question_result = safe_execute(
                        "process_question",
                        self._prepare_question_data,
                        q, request,
                        error_collector=error_collector
                    )
                    
                    if question_result:
                        question_data, answers_data = question_result
                        questions_data.append(question_data)
                        question_answers_data.extend(answers_data)
                
                for f in flashcards:
                    flashcard_result = safe_execute(
                        "process_flashcard",
                        self._prepare_flashcard_data,
                        f, request,
                        error_collector=error_collector
                    )
                    
                    if flashcard_result:
                        flashcards_data.append(flashcard_result)
                
                if questions_data:
                    BatchOperations.bulk_insert_questions(db, questions_data)
                
                if flashcards_data:
                    BatchOperations.bulk_insert_flashcards(db, flashcards_data)
                
                if question_answers_data:
                    self._insert_question_answers(db, question_answers_data)
                
                session_summary = None
                if request.session_id:
                    try:
                        summary_service.generate_or_update_summary(db, request.session_id, regenerate=False)
                        session_summary = summary_service.get_session_summary(db, request.session_id)
                        logger.info(f"Summary auto-generated/updated for session {request.session_id}")
                    except Exception as e:
                        logger.warning(f"Failed to auto-generate summary for session {request.session_id}: {e}")

                if error_collector.has_errors():
                    error_summary = error_collector.get_summary()
                    logger.warning(f"Processing completed with errors: {error_summary}")
                    op.add_metadata(processing_errors=error_summary['total_errors'])

                result = {
                    "topic": request.topic,
                    "document_ids": request.document_ids,
                    "session_id": request.session_id,
                    "questions": questions,
                    "flashcards": flashcards,
                    "summary": session_summary,
                    "context_used": relevant_context[:200] + "..." if len(relevant_context) > 200 else relevant_context,
                    "created_at": current_date_time(),
                    "processing_stats": {
                        "questions_requested": request.quiz_count,
                        "questions_generated": len(questions),
                        "questions_saved": len(questions_data),
                        "flashcards_requested": request.flashcard_count,
                        "flashcards_generated": len(flashcards),
                        "flashcards_saved": len(flashcards_data),
                        "errors": error_collector.get_summary() if error_collector.has_errors() else None
                    }
                }
                
                op.add_metadata(
                    questions_saved=len(questions_data),
                    flashcards_saved=len(flashcards_data),
                    processing_success=True
                )
                
                return result

            except Exception as e:
                op.add_metadata(processing_success=False, error=str(e))
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=str(e))
    def _prepare_question_data(self, q, request) -> tuple:
        """Prepare question data for batch insertion"""
        question_id = str(uuid.uuid4())
        
        quality_score = self.question_generator.calculate_quality_score(
            {"question": q.question, "answer": q.correct_answer, "explanation": q.explanation}, 
            q.source_context
        )
        
        question_data = {
            "id": question_id,
            "content": q.question,
            "type": q.type,
            "difficulty_level": q.difficulty_level,
            "topic": q.topic,
            "correct_answer": q.correct_answer,
            "session_id": request.session_id,
            "user_id": request.user_id,
            "explanation": q.explanation,
            "source_context": q.source_context,
            "generation_model": self.question_generator.model_name,
            "validation_score": quality_score,
            "created_at": current_date_time(),
        }
        
        answers_data = []
        for ans in q.answers:
            answers_data.append({
                "id": str(uuid.uuid4()),
                "content": ans.content,
                "is_correct": ans.is_correct,
                "explanation": ans.explanation,
                "question_id": question_id,
            })
        
        return question_data, answers_data
    
    def _prepare_flashcard_data(self, f, request) -> dict:
        """Prepare flashcard data for batch insertion"""
        quality_score = self.question_generator.calculate_quality_score(
            {"question": f.question, "answer": f.answer, "explanation": f.explanation}, 
            f.source_context
        )
        
        return {
            "id": str(uuid.uuid4()),
            "card_type": f.card_type,
            "question": f.question,
            "answer": f.answer,
            "explanation": f.explanation,
            "topic": f.topic,
            "source_context": f.source_context,
            "generation_model": self.question_generator.model_name,
            "validation_score": quality_score,
            "session_id": request.session_id,
            "user_id": request.user_id,
            "created_at": current_date_time(),
        }
    
    def _insert_question_answers(self, db: Session, answers_data: list):
        """Insert question answers (requires existing questions)"""
        try:
            from app.models import QuestionAnswer
            db.bulk_insert_mappings(QuestionAnswer, answers_data)
            db.commit()
            logger.info(f"Inserted {len(answers_data)} question answers")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to insert question answers: {e}")
            raise
            
question_service = QuestionService()