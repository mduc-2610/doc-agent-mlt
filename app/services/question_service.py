import uuid
import logging
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException
from app.models import Question, QuestionAnswer, Flashcard
from app.config import current_date_time

logger = logging.getLogger(__name__)

class QuestionService:
    
    def get_questions_by_session(self, db: Session, session_id: str):
        return (
            db.query(Question)
            .options(joinedload(Question.question_answers))
            .filter(Question.session_id == session_id)
            .all()
        )

    def get_flashcards_by_session(self, db: Session, session_id: str):
        return db.query(Flashcard).filter(Flashcard.session_id == session_id).all()

    def create_question(self, db: Session, question_data: dict) -> Question:
        question = Question(
            id=str(uuid.uuid4()),
            content=question_data['content'],
            type=question_data['type'],
            correct_answer=question_data['correct_answer'],
            explanation=question_data.get('explanation'),
            topic=question_data.get('topic'),
            difficulty_level=question_data.get('difficulty_level'),
            session_id=question_data['session_id'],
            created_at=current_date_time()
        )
        db.add(question)
        db.flush()
        
        if 'question_answers' in question_data and question_data['question_answers']:
            for answer_data in question_data['question_answers']:
                db.add(QuestionAnswer(
                    id=str(uuid.uuid4()),
                    content=answer_data['content'],
                    is_correct=answer_data.get('is_correct', False),
                    explanation=answer_data.get('explanation'),
                    question_id=question.id
                ))
        
        db.commit()
        db.refresh(question)
        return question

    def create_flashcard(self, db: Session, flashcard_data: dict) -> Flashcard:
        flashcard = Flashcard(
            id=str(uuid.uuid4()),
            question=flashcard_data['question'],
            answer=flashcard_data['answer'],
            card_type=flashcard_data['card_type'],
            explanation=flashcard_data.get('explanation'),
            topic=flashcard_data.get('topic'),
            session_id=flashcard_data['session_id'],
            created_at=current_date_time()
        )
        db.add(flashcard)
        db.commit()
        db.refresh(flashcard)
        return flashcard

    def update_question(self, db: Session, question_id: str, update_data: dict) -> Question:
        question = db.query(Question).filter(Question.id == question_id).first()
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        
        for field, value in update_data.items():
            if field != 'question_answers' and hasattr(question, field):
                setattr(question, field, value)
        
        if 'question_answers' in update_data:
            db.query(QuestionAnswer).filter(QuestionAnswer.question_id == question_id).delete()
            for answer_data in update_data['question_answers']:
                db.add(QuestionAnswer(
                    id=str(uuid.uuid4()),
                    content=answer_data['content'], 
                    is_correct=answer_data.get('is_correct', False),
                    explanation=answer_data.get('explanation'),
                    question_id=question_id
                ))
        
        db.commit()
        db.refresh(question)
        return question

    def update_flashcard(self, db: Session, flashcard_id: str, update_data: dict) -> Flashcard:
        flashcard = db.query(Flashcard).filter(Flashcard.id == flashcard_id).first()
        if not flashcard:
            raise HTTPException(status_code=404, detail="Flashcard not found")
        
        for field, value in update_data.items():
            if hasattr(flashcard, field):
                setattr(flashcard, field, value)
        
        db.commit()
        db.refresh(flashcard)
        return flashcard

    def delete_question(self, db: Session, question_id: str) -> bool:
        question = db.query(Question).filter(Question.id == question_id).first()
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        db.delete(question)
        db.commit()
        return True

    def delete_flashcard(self, db: Session, flashcard_id: str) -> bool:
        flashcard = db.query(Flashcard).filter(Flashcard.id == flashcard_id).first()
        if not flashcard:
            raise HTTPException(status_code=404, detail="Flashcard not found")
        db.delete(flashcard)
        db.commit()
        return True

question_service = QuestionService()