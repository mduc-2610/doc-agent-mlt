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

router = APIRouter()


@router.get("/questions/by-session/{session_id}", response_model=List[QuestionResponse])
async def get_question_by_session(session_id: str, db: Session = Depends(get_db)):
    try:
        questions = question_service.get_questions_by_session(db, session_id)
        return [QuestionResponse.model_validate(q) for q in questions]
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    

@router.get("/flashcards/by-session/{session_id}", response_model=List[FlashcardResponse])
async def get_flashcards_by_session(session_id: str, db: Session = Depends(get_db)):
    try:
        flashcards = question_service.get_flashcards_by_session(db, session_id)
        return [FlashcardResponse.model_validate(f) for f in flashcards]
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/questions/by-document/{document_id}", response_model=List[QuestionResponse])
async def get_question_by_document(document_id: str, db: Session = Depends(get_db)):
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

@router.delete("/questions/by-document/{document_id}")
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

@router.post("/generate/file")
async def generate_question_from_file(
    request: DocumentFileUploadRequest = Depends(as_form(DocumentFileUploadRequest)),
    db: Session = Depends(get_db)
):
    return question_service.generate_question_from_file_service(request=request, db=db)

@router.post("/generate/url")
async def generate_question_from_url(
    request: DocumentUrlUploadRequest = Depends(as_form(DocumentUrlUploadRequest)),
    db: Session = Depends(get_db)
):
    return question_service.generate_question_from_url_service(request=request, db=db)