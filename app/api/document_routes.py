import os
import traceback
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.document_service import document_service
from datetime import datetime
from app.schemas.document import (
    FileParseRequest,
    SessionCreateRequest,
    SessionUpdateRequest,
    SessionDetailResponse,
    DocumentResponse,
    SessionResponse,
    MessageResponse,
    UrlParseRequest,
)
from app.utils.helper import as_form

router = APIRouter()

@router.get("/sessions", response_model=List[SessionResponse])
def get_sessions(db: Session = Depends(get_db)):
    try:
        sessions = document_service.get_sessions(db)
        return [SessionResponse.model_validate(s) for s in sessions]
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sessions", response_model=SessionResponse)
async def create_session(request: SessionCreateRequest = Depends(as_form(SessionCreateRequest)), db: Session = Depends(get_db)):
    try:
        session = document_service.create_session(
            db, request.user_id, request.name, request.description
        )
        return SessionResponse.model_validate(session)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(session_id: str, db: Session = Depends(get_db)):
    try:
        session = document_service.get_session(db, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return SessionDetailResponse.model_validate(session)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sessions/user/{user_id}", response_model=List[SessionResponse])
async def get_user_sessions(user_id: str, db: Session = Depends(get_db)):
    try:
        sessions = document_service.get_user_sessions(db, user_id)
        return [SessionResponse.model_validate(s) for s in sessions]
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/sessions/{session_id}", response_model=MessageResponse)
async def update_session(session_id: str, request: SessionUpdateRequest = Depends(as_form(SessionUpdateRequest)), db: Session = Depends(get_db)):
    try:
        document_service.update_session(db, session_id, request.name, request.description)
        return MessageResponse(message="Session updated successfully")
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/sessions/{session_id}", response_model=MessageResponse)
async def delete_session(session_id: str, db: Session = Depends(get_db)):
    try:
        document_service.delete_session(db, session_id)
        return MessageResponse(message="Deleted successfully")
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/document", response_model=DocumentResponse)
async def parse_document(
    request: FileParseRequest = Depends(as_form(FileParseRequest)),
    db: Session = Depends(get_db)
):
    try:
        document = document_service.parse_document(db, request=request)
        return DocumentResponse.model_validate(document)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/audio-video", response_model=DocumentResponse)
async def parse_audio_video(
    request: FileParseRequest = Depends(as_form(FileParseRequest)),
    db: Session = Depends(get_db)
):
    try:
        document = document_service.parse_audio_video(db, request=request)
        return DocumentResponse.model_validate(document)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/web-url", response_model=DocumentResponse)
async def parse_web_url(request: UrlParseRequest = Depends(as_form(UrlParseRequest)), db: Session = Depends(get_db)):
    try:
        document = document_service.parse_web_url(db, request=request)
        return DocumentResponse.model_validate(document)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/youtube", response_model=DocumentResponse)
async def parse_youtube(request: UrlParseRequest = Depends(as_form(UrlParseRequest)), db: Session = Depends(get_db)):
    try:
        document = document_service.parse_youtube(db, request=request)
        return DocumentResponse.model_validate(document)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str, db: Session = Depends(get_db)):
    try:
        doc = document_service.get_document(db, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        return DocumentResponse.model_validate(doc)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents", response_model=List[DocumentResponse])
async def get_documents(db: Session = Depends(get_db)):
    try:
        docs = document_service.get_documents(db)
        return [DocumentResponse.model_validate(d) for d in docs]
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents/session/{session_id}", response_model=List[DocumentResponse])
async def get_documents_by_session(session_id: str, db: Session = Depends(get_db)):
    try:
        docs = document_service.get_documents_by_session(db, session_id)
        return [DocumentResponse.model_validate(d) for d in docs]
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))