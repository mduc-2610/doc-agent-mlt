from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import Optional, List
import traceback
from pydantic import BaseModel
from typing import Optional, List
from app.request_response.question import (
    TopicGenerationRequest,
    QuestionResponse,
    FlashcardResponse,
    DocumentFileUploadRequest,
)

from app.database import get_db
from app.services.question_service import question_service

router = APIRouter()

@router.post("/generate/topic")
async def generate_quiz_from_topic(
    request: TopicGenerationRequest,
    db: Session = Depends(get_db)
):
    try:
        return question_service.process_rag_quiz_and_flashcards(
            topic=request.topic,
            document_ids=request.document_ids,
            session_id=request.session_id,
            user_id=request.user_id,
            quiz_count=request.quiz_count,
            flashcard_count=request.flashcard_count,
            db=db
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/by-document/{document_id}", response_model=List[QuestionResponse])
async def get_quiz_by_document(document_id: str, db: Session = Depends(get_db)):
    try:
        questions = question_service.get_questions_by_document(db, document_id)
        return [QuestionResponse.model_validate(q) for q in questions]
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/flashcards/by-document/{document_id}", response_model=List[FlashcardResponse])
async def get_flashcards_by_document(document_id: str, db: Session = Depends(get_db)):
    try:
        flashcards = question_service.get_flashcards_by_document(db, document_id)
        return [FlashcardResponse.model_validate(f) for f in flashcards]
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/by-document/{document_id}")
async def delete_questions_by_document(document_id: str, db: Session = Depends(get_db)):
    try:
        question_service.delete_questions_by_document(db, document_id)
        return {"message": f"Questions deleted for document {document_id}"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/flashcards/by-document/{document_id}")
async def delete_flashcards_by_document(document_id: str, db: Session = Depends(get_db)):
    try:
        question_service.delete_flashcards_by_document(db, document_id)
        return {"message": f"Flashcards deleted for document {document_id}"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
        

@router.post("/generate/url")
async def generate_question_from_url(
    request=DocumentFileUploadRequest,
    db: Session = Depends(get_db)
):
    
    return question_service.generate_question_from_url_service(
        request=request,
        db=db,
    )


@router.post("/generate/file")
async def generate_question_from_file(
    request=DocumentFileUploadRequest,
    db: Session = Depends(get_db)
):
    return question_service.generate_question_from_file_service(
        request=request,
        db=db,
    )