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

    def update_question(self, db: Session, question_id: str, update_data: dict) -> Question:
        """Update a question and its answers"""
        try:
            question = db.query(Question).filter(Question.id == question_id).first()
            if not question:
                raise HTTPException(status_code=404, detail="Question not found")
            
            # Update question fields
            for field, value in update_data.items():
                if field != 'question_answers' and hasattr(question, field):
                    setattr(question, field, value)
            
            # Update question answers if provided
            if 'question_answers' in update_data:
                # Delete existing answers
                db.query(QuestionAnswer).filter(QuestionAnswer.question_id == question_id).delete()
                
                # Add new answers
                for answer_data in update_data['question_answers']:
                    new_answer = QuestionAnswer(
                        id=str(uuid.uuid4()),
                        content=answer_data['content'],
                        is_correct=answer_data.get('is_correct', False),
                        explanation=answer_data.get('explanation'),
                        question_id=question_id
                    )
                    db.add(new_answer)
            
            db.commit()
            db.refresh(question)
            return question
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update question {question_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def update_flashcard(self, db: Session, flashcard_id: str, update_data: dict) -> Flashcard:
        """Update a flashcard"""
        try:
            flashcard = db.query(Flashcard).filter(Flashcard.id == flashcard_id).first()
            if not flashcard:
                raise HTTPException(status_code=404, detail="Flashcard not found")
            
            # Update flashcard fields
            for field, value in update_data.items():
                if hasattr(flashcard, field):
                    setattr(flashcard, field, value)
            
            db.commit()
            db.refresh(flashcard)
            return flashcard
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update flashcard {flashcard_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def delete_question(self, db: Session, question_id: str) -> bool:
        """Delete a question and its answers"""
        try:
            question = db.query(Question).filter(Question.id == question_id).first()
            if not question:
                raise HTTPException(status_code=404, detail="Question not found")
            
            db.delete(question)
            db.commit()
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete question {question_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def delete_flashcard(self, db: Session, flashcard_id: str) -> bool:
        """Delete a flashcard"""
        try:
            flashcard = db.query(Flashcard).filter(Flashcard.id == flashcard_id).first()
            if not flashcard:
                raise HTTPException(status_code=404, detail="Flashcard not found")
            
            db.delete(flashcard)
            db.commit()
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete flashcard {flashcard_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def create_question(self, db: Session, question_data: dict) -> Question:
        """Create a new question"""
        try:
            question = Question(
                id=str(uuid.uuid4()),
                content=question_data['content'],
                type=question_data['type'],
                correct_answer=question_data['correct_answer'],
                explanation=question_data.get('explanation'),
                topic=question_data.get('topic'),
                difficulty_level=question_data.get('difficulty_level'),
                session_id=question_data['session_id'],
                user_id=question_data['user_id'],
                created_at=current_date_time()
            )
            
            db.add(question)
            db.flush()  # To get the ID
            
            # Add question answers if provided
            if 'question_answers' in question_data and question_data['question_answers']:
                for answer_data in question_data['question_answers']:
                    answer = QuestionAnswer(
                        id=str(uuid.uuid4()),
                        content=answer_data['content'],
                        is_correct=answer_data.get('is_correct', False),
                        explanation=answer_data.get('explanation'),
                        question_id=question.id
                    )
                    db.add(answer)
            
            db.commit()
            db.refresh(question)
            return question
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create question: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def create_flashcard(self, db: Session, flashcard_data: dict) -> Flashcard:
        """Create a new flashcard"""
        try:
            flashcard = Flashcard(
                id=str(uuid.uuid4()),
                question=flashcard_data['question'],
                answer=flashcard_data['answer'],
                card_type=flashcard_data['card_type'],
                explanation=flashcard_data.get('explanation'),
                topic=flashcard_data.get('topic'),
                session_id=flashcard_data['session_id'],
                user_id=flashcard_data['user_id'],
                created_at=current_date_time()
            )
            
            db.add(flashcard)
            db.commit()
            db.refresh(flashcard)
            return flashcard
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create flashcard: {e}")
            raise HTTPException(status_code=500, detail=str(e))

question_service = QuestionService()