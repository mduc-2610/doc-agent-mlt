from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import Optional, List
import traceback
from app.schemas.question import (
    QuestionGenerationRequest,
    QuestionResponse,
    FlashcardResponse,
    QuestionUpdateRequest,
    FlashcardUpdateRequest,
    QuestionCreateRequest,
    FlashcardCreateRequest,
)
from app.schemas.message import MessageResponse
from app.config import settings
from app.database import get_db
from app.services.question_service import question_service
from app.services.question_gen_service import question_gen_service
from app.utils.helper import as_form

router = APIRouter()

@router.get("/questions/by-session/{session_id}", response_model=List[QuestionResponse])
async def get_question_by_session(session_id: str, db: Session = Depends(get_db)):
    questions = question_service.get_questions_by_session(db, session_id)
    return [QuestionResponse.model_validate(q) for q in questions]

@router.get("/flashcards/by-session/{session_id}", response_model=List[FlashcardResponse])
async def get_flashcards_by_session(session_id: str, db: Session = Depends(get_db)):
    flashcards = question_service.get_flashcards_by_session(db, session_id)
    return [FlashcardResponse.model_validate(f) for f in flashcards]
    
@router.post("/generate/batch")
async def batch_generate_questions(
    request: QuestionGenerationRequest,
    db: Session = Depends(get_db)
):
    if request.topic and len(request.topic.strip()) > 100:
        raise HTTPException(
            status_code=400, 
            detail=MessageResponse.create(
                translation_key="topicTooLong",
                message="Topic must be 100 characters or less"
            ).model_dump()
        )
    
    if request.quiz_count < 1 or request.quiz_count > settings.generation.max_questions_per_request:
        raise HTTPException(
            status_code=400, 
            detail=MessageResponse.create(
                translation_key="invalidQuestionCount",
                message=f"Quiz count cannot exceed {settings.generation.max_questions_per_request}"
            ).model_dump()
        )
    if request.flashcard_count < 1 or request.flashcard_count > settings.generation.max_flashcards_per_request:
        raise HTTPException(
            status_code=400, 
            detail=MessageResponse.create(
                translation_key="invalidFlashcardCount",
                message=f"Flashcard count cannot exceed {settings.generation.max_flashcards_per_request}"
            ).model_dump()
        )
    
    return question_gen_service.process_rag_quiz_and_flashcards(request, db)

@router.put("/questions/{question_id}", response_model=QuestionResponse)
async def update_question(
    question_id: str,
    request: QuestionUpdateRequest,
    db: Session = Depends(get_db)
):
    updated_question = question_service.update_question(
        db, question_id, request.model_dump(exclude_unset=True)
    )
    return QuestionResponse.model_validate(updated_question)

@router.delete("/questions/{question_id}")
async def delete_question(question_id: str, db: Session = Depends(get_db)):
    question_service.delete_question(db, question_id)
    return {"message": "Question deleted successfully"}

@router.put("/flashcards/{flashcard_id}", response_model=FlashcardResponse)
async def update_flashcard(
    flashcard_id: str,
    request: FlashcardUpdateRequest,
    db: Session = Depends(get_db)
):
    updated_flashcard = question_service.update_flashcard(
        db, flashcard_id, request.model_dump(exclude_unset=True)
    )
    return FlashcardResponse.model_validate(updated_flashcard)

@router.delete("/flashcards/{flashcard_id}")
async def delete_flashcard(flashcard_id: str, db: Session = Depends(get_db)):
    question_service.delete_flashcard(db, flashcard_id)
    return {"message": "Flashcard deleted successfully"}

@router.post("/questions", response_model=QuestionResponse)
async def create_question(
    request: QuestionCreateRequest,
    db: Session = Depends(get_db)
):
    created_question = question_service.create_question(
        db, request.model_dump()
    )
    return QuestionResponse.model_validate(created_question)

@router.post("/flashcards", response_model=FlashcardResponse)
async def create_flashcard(
    request: FlashcardCreateRequest,
    db: Session = Depends(get_db)
):
    created_flashcard = question_service.create_flashcard(
        db, request.model_dump()
    )
    return FlashcardResponse.model_validate(created_flashcard)