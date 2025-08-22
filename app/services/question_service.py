# app/services/question_service.py - Simplified question service
import uuid
import traceback
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException
from typing import Dict, Any
from app.models import Question, QuestionAnswer, Flashcard
import logging
from app.config import current_date_time
from app.processors.question_generator import question_generator
from app.schemas.question import QuestionGenerationRequest
from app.processors.vector_processor import vector_processor
from app.database import bulk_insert_questions, bulk_insert_flashcards

logger = logging.getLogger(__name__)

class QuestionService:
    def __init__(self):
        self.question_generator = question_generator
        self.vector_processor = vector_processor

    def get_questions_by_session(self, db: Session, session_id: str):
        return (
            db.query(Question)
            .options(joinedload(Question.question_answers))
            .filter(Question.session_id == session_id)
            .all()
        )

    def get_flashcards_by_session(self, db: Session, session_id: str):
        return db.query(Flashcard).filter(Flashcard.session_id == session_id).all()

    def process_rag_quiz_and_flashcards(self, request: QuestionGenerationRequest, db: Session) -> Dict[str, Any]:
        try:
            relevant_context = self.vector_processor.get_relevant_context(
                db, request.topic, request.document_ids, max_context_length=4000
            )
            
            if not relevant_context.strip():
                raise HTTPException(status_code=400, detail="No relevant context found")

            questions = self.question_generator.generate_rag_quiz(
                request.topic, relevant_context, request.quiz_count
            )
            flashcards = self.question_generator.generate_rag_flashcards(
                request.topic, relevant_context, request.flashcard_count
            )
            
            questions_data = []
            flashcards_data = []
            question_answers_data = []
            
            for q in questions:
                question_id = str(uuid.uuid4())
                
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
                    "validation_score": self._calculate_quality_score(q),
                    "created_at": current_date_time(),
                }
                questions_data.append(question_data)
                
                for ans in q.answers:
                    question_answers_data.append({
                        "id": str(uuid.uuid4()),
                        "content": ans.content,
                        "is_correct": ans.is_correct,
                        "explanation": ans.explanation,
                        "question_id": question_id,
                    })
            
            for f in flashcards:
                flashcard_data = {
                    "id": str(uuid.uuid4()),
                    "card_type": f.card_type,
                    "question": f.question,
                    "answer": f.answer,
                    "explanation": f.explanation,
                    "topic": f.topic,
                    "source_context": f.source_context,
                    "generation_model": self.question_generator.model_name,
                    "validation_score": self._calculate_quality_score(f),
                    "session_id": request.session_id,
                    "user_id": request.user_id,
                    "created_at": current_date_time(),
                }
                flashcards_data.append(flashcard_data)
            
            if questions_data:
                bulk_insert_questions(db, questions_data)
            
            if flashcards_data:
                bulk_insert_flashcards(db, flashcards_data)
            
            if question_answers_data:
                self._insert_question_answers(db, question_answers_data)

            result = {
                "topic": request.topic,
                "document_ids": request.document_ids,
                "session_id": request.session_id,
                "questions": questions,
                "flashcards": flashcards,
                "context_used": relevant_context[:200] + "..." if len(relevant_context) > 200 else relevant_context,
                "created_at": current_date_time(),
                "processing_stats": {
                    "questions_requested": request.quiz_count,
                    "questions_generated": len(questions),
                    "questions_saved": len(questions_data),
                    "flashcards_requested": request.flashcard_count,
                    "flashcards_generated": len(flashcards),
                    "flashcards_saved": len(flashcards_data),
                }
            }
            
            return result

        except Exception as e:
            logger.error(f"Question generation failed: {e}")
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    
    def _calculate_quality_score(self, content) -> float:
        try:
            question = getattr(content, 'question', '')
            answer = getattr(content, 'answer', getattr(content, 'correct_answer', ''))
            explanation = getattr(content, 'explanation', '')
            
            score = 0.0
            
            if len(question) > 10:
                score += 0.3
            if len(answer) > 5:
                score += 0.3
            if len(explanation) > 10:
                score += 0.4
            
            return min(score, 1.0)
        except Exception:
            return 0.5  
    
    def _insert_question_answers(self, db: Session, answers_data: list):
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