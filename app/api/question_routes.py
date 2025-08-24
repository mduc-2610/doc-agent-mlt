from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import Optional, List
import traceback
from app.schemas.question import (
    QuestionGenerationRequest,
    QuestionResponse,
    FlashcardResponse,
    DocumentFileUploadRequest,
    DocumentUrlUploadRequest,
    QuestionUpdateRequest,
    FlashcardUpdateRequest,
    QuestionCreateRequest,
    FlashcardCreateRequest,
)

from app.database import get_db
from app.services.question_service import question_service
from app.utils.helper import as_form
from app.utils.error_handling import handle_database_errors, handle_llm_errors

router = APIRouter()

@router.get("/questions/by-session/{session_id}", response_model=List[QuestionResponse])
@handle_database_errors
async def get_question_by_session(session_id: str, db: Session = Depends(get_db)):
    questions = question_service.get_questions_by_session(db, session_id)
    return [QuestionResponse.model_validate(q) for q in questions]

@router.get("/flashcards/by-session/{session_id}", response_model=List[FlashcardResponse])
@handle_database_errors
async def get_flashcards_by_session(session_id: str, db: Session = Depends(get_db)):
    flashcards = question_service.get_flashcards_by_session(db, session_id)
    return [FlashcardResponse.model_validate(f) for f in flashcards]
    
@router.post("/generate/batch")
@handle_llm_errors
@handle_database_errors
async def batch_generate_questions(
    request: QuestionGenerationRequest,
    db: Session = Depends(get_db)
):
    return question_service.process_rag_quiz_and_flashcards(request, db)

@router.post("/cache/clear")
async def clear_generation_cache():
    """Clear question generation cache"""
    from app.processors.question_generator import question_generator
    cleared_count = question_generator.clear_cache()
    return {"message": f"Cleared {cleared_count} cached responses"}

@router.put("/questions/{question_id}", response_model=QuestionResponse)
@handle_database_errors
async def update_question(
    question_id: str,
    request: QuestionUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update a question"""
    updated_question = question_service.update_question(
        db, question_id, request.model_dump(exclude_unset=True)
    )
    return QuestionResponse.model_validate(updated_question)

@router.delete("/questions/{question_id}")
@handle_database_errors
async def delete_question(question_id: str, db: Session = Depends(get_db)):
    """Delete a question"""
    question_service.delete_question(db, question_id)
    return {"message": "Question deleted successfully"}

@router.put("/flashcards/{flashcard_id}", response_model=FlashcardResponse)
@handle_database_errors
async def update_flashcard(
    flashcard_id: str,
    request: FlashcardUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update a flashcard"""
    updated_flashcard = question_service.update_flashcard(
        db, flashcard_id, request.model_dump(exclude_unset=True)
    )
    return FlashcardResponse.model_validate(updated_flashcard)

@router.delete("/flashcards/{flashcard_id}")
@handle_database_errors
async def delete_flashcard(flashcard_id: str, db: Session = Depends(get_db)):
    """Delete a flashcard"""
    question_service.delete_flashcard(db, flashcard_id)
    return {"message": "Flashcard deleted successfully"}

@router.post("/questions", response_model=QuestionResponse)
@handle_database_errors
async def create_question(
    request: QuestionCreateRequest,
    db: Session = Depends(get_db)
):
    """Create a new question"""
    created_question = question_service.create_question(
        db, request.model_dump()
    )
    return QuestionResponse.model_validate(created_question)

@router.post("/flashcards", response_model=FlashcardResponse)
@handle_database_errors
async def create_flashcard(
    request: FlashcardCreateRequest,
    db: Session = Depends(get_db)
):
    """Create a new flashcard"""
    created_flashcard = question_service.create_flashcard(
        db, request.model_dump()
    )
    return FlashcardResponse.model_validate(created_flashcard)