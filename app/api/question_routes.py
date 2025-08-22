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