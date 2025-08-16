import uuid
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, UploadFile
from app.models import Question, QuestionAnswer, Flashcard
import logging
from app.config import current_date_time

logger = logging.getLogger(__name__)

def get_questions_by_document(db, document_id: str):
    return (
        db.query(Question)
        .options(joinedload(Question.question_answers))
        .filter(Question.document_id == document_id)
        .all()
    )

def get_flashcards_by_document(db: Session, document_id: str):
    return db.query(Flashcard).filter(Flashcard.document_id == document_id).all()

def delete_questions_by_document(db: Session, document_id: str):
    db.query(Question).filter(Question.document_id == document_id).delete()
    db.commit()

def delete_flashcards_by_document(db: Session, document_id: str):
    db.query(Flashcard).filter(Flashcard.document_id == document_id).delete()
    db.commit()
