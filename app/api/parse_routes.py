import os
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.services import document_service
import traceback

router = APIRouter()

@router.post("/sessions")
async def create_session(
    user_id: str = Form(...), 
    name: str = Form(...), 
    description: str = Form(""),
    db: Session = Depends(get_db)
):
    try:
        session = document_service.create_session(db, user_id, name, description)
        return {
            "session_id": str(session.id),
            "user_id": session.user_id,
            "name": session.name,
            "description": session.description,
            "document_count": 0,
            "created_at": session.created_at
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sessions/{session_id}")
async def get_session(session_id: str, db: Session = Depends(get_db)):
    try:
        session = document_service.get_session(db, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        documents = document_service.get_documents_by_session(db, session_id)
        
        return {
            "session_id": str(session.id),
            "user_id": session.user_id,
            "name": session.name,
            "description": session.description,
            "document_count": len(documents),
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "documents": [
                {
                    "document_id": str(doc.id),
                    "filename": doc.filename,
                    "file_type": doc.file_type,
                    "source_type": doc.source_type,
                    "status": doc.processing_status,
                    "created_at": doc.created_at,
                    "text_length": doc.text_length
                } for doc in documents
            ]
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sessions/user/{user_id}")
async def get_user_sessions(user_id: str, db: Session = Depends(get_db)):
    try:
        sessions = document_service.get_user_sessions(db, user_id)
        
        result = []
        for session in sessions:
            documents = document_service.get_documents_by_session(db, str(session.id))
            result.append({
                "session_id": str(session.id),
                "user_id": session.user_id,
                "name": session.name,
                "description": session.description,
                "document_count": len(documents),
                "created_at": session.created_at,
                "updated_at": session.updated_at
            })
        
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/sessions/{session_id}")
async def update_session(
    session_id: str, 
    name: str = Form(None), 
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    try:
        document_service.update_session(db, session_id, name, description)
        return {"message": "Session updated successfully"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, db: Session = Depends(get_db)):
    try:
        document_service.delete_session(db, session_id)
        return {"message": "Session and all associated documents deleted successfully"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/document")
async def parse_document(
    file: UploadFile = File(...), 
    session_id: str = Form(None),
    db: Session = Depends(get_db)
):
    try:
        document = document_service.parse_document(db, file, session_id)
        return {
            "document_id": str(document.id),
            "filename": document.filename,
            "file_type": document.file_type,
            "status": document.processing_status,
            "text_length": document.text_length,
            "session_id": str(document.session_id) if document.session_id else None
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/audio-video")
async def parse_audio_video(
    file: UploadFile = File(...), 
    session_id: str = Form(None),
    db: Session = Depends(get_db)
):
    try:
        document = document_service.parse_audio_video(db, file, session_id)
        return {
            "document_id": str(document.id),
            "filename": document.filename,
            "file_type": document.file_type,
            "status": document.processing_status,
            "text_length": document.text_length,
            "session_id": str(document.session_id) if document.session_id else None
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/web-url")
async def parse_web_url(
    url: str = Form(...), 
    session_id: str = Form(None),
    db: Session = Depends(get_db)
):
    try:
        document = document_service.parse_web_url(db, url, session_id)
        return {
            "document_id": str(document.id),
            "url": url,
            "file_type": document.file_type,
            "status": document.processing_status,
            "text_length": document.text_length,
            "session_id": str(document.session_id) if document.session_id else None
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/youtube")
async def parse_youtube(
    url: str = Form(...), 
    session_id: str = Form(None),
    db: Session = Depends(get_db)
):
    try:
        document = document_service.parse_youtube(db, url, session_id)
        return {
            "document_id": str(document.id),
            "youtube_url": url,
            "file_type": document.file_type,
            "status": document.processing_status,
            "text_length": document.text_length,
            "session_id": str(document.session_id) if document.session_id else None
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/document/{document_id}")
async def get_document(document_id: str, db: Session = Depends(get_db)):
    try:
        doc = document_service.get_document(db, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        raw_text = ""
        if doc.content_file_path and os.path.exists(doc.content_file_path):
            with open(doc.content_file_path, 'r', encoding='utf-8') as f:
                raw_text = f.read()
        
        return {
            "document_id": str(doc.id),
            "filename": doc.filename,
            "file_type": doc.file_type,
            "source_type": doc.source_type,
            "status": doc.processing_status,
            "created_at": doc.created_at,
            "text_length": doc.text_length,
            "session_id": str(doc.session_id) if doc.session_id else None,
            "raw_text": raw_text
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents")
async def get_documents(db: Session = Depends(get_db)):
    try:
        docs = document_service.get_documents(db)
        return [
            {
                "document_id": str(doc.id),
                "filename": doc.filename,
                "file_type": doc.file_type,
                "source_type": doc.source_type,
                "status": doc.processing_status,
                "created_at": doc.created_at,
                "text_length": doc.text_length,
                "session_id": str(doc.session_id) if doc.session_id else None
            } for doc in docs
        ]
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents/session/{session_id}")
async def get_documents_by_session(session_id: str, db: Session = Depends(get_db)):
    try:
        docs = document_service.get_documents_by_session(db, session_id)
        return [
            {
                "document_id": str(doc.id),
                "filename": doc.filename,
                "file_type": doc.file_type,
                "file_size": doc.file_size,
                "source_type": doc.source_type,
                "status": doc.processing_status,
                "created_at": doc.created_at,
                "text_length": doc.text_length,
                "session_id": str(doc.session_id) if doc.session_id else None
            } for doc in docs
        ]
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))