from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.services import quiz_service, gen_service
import traceback

router = APIRouter()

@router.get("/by-document/{document_id}")
async def get_quiz_by_document(document_id: str, db: Session = Depends(get_db)):
    try:
        questions = quiz_service.get_questions_by_document(db, document_id)
        
        return {
            "document_id": document_id,
            "quiz_questions": questions,
            "total_questions": len(questions)
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/flashcards/by-document/{document_id}")
async def get_flashcards_by_document(document_id: str, db: Session = Depends(get_db)):
    try:
        flashcards = quiz_service.get_flashcards_by_document(db, document_id)
    
        return {
            "document_id": document_id,
            "flashcards": flashcards,
            "total_flashcards": len(flashcards)
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
        
@router.delete("/by-document/{document_id}")
async def delete_quiz_by_document(document_id: str, db: Session = Depends(get_db)):
    try:
        quiz_service.delete_questions_by_document(db, document_id)
        return {"message": f"Quiz deleted for document {document_id}"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/flashcards/by-document/{document_id}")
async def delete_flashcards_by_document(document_id: str, db: Session = Depends(get_db)):
    try:
        quiz_service.delete_flashcards_by_document(db, document_id)
        return {"message": f"Flashcards deleted for document {document_id}"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate/url")
async def generate_quiz_from_url(
    url: str = Form(...), 
    user_id: str = Form(...),
    session_id: Optional[str] = Form(None),
    quiz_count: int = Form(15), 
    flashcard_count: int = Form(15), 
    target_chunks: int = Form(5),
    db: Session = Depends(get_db)
):
    return gen_service.generate_quiz_from_url_service(
        url=url,
        user_id=user_id,
        session_id=session_id,
        quiz_count=quiz_count,
        flashcard_count=flashcard_count,
        target_chunks=target_chunks,
        db=db,
    )

@router.post("/generate/file")
async def generate_quiz_from_file(
    file: UploadFile = File(...), 
    user_id: str = Form(...),
    session_id: Optional[str] = Form(None),
    quiz_count: int = Form(15),
    flashcard_count: int = Form(15), 
    target_chunks: int = Form(5),
    db: Session = Depends(get_db)
):
    return gen_service.generate_quiz_from_file_service(
        file=file,
        user_id=user_id,
        session_id=session_id,
        quiz_count=quiz_count,
        flashcard_count=flashcard_count,
        target_chunks=target_chunks,
        db=db,
    )