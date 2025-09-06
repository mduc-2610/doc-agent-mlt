import os
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.message import MessageResponse
from app.services.document_service import document_service
from app.services.document_process_service import document_process_service
from datetime import datetime
from app.schemas.document import (
    FileParseRequest,
    DocumentResponse,
    UrlParseRequest,
)
from app.schemas.common import MessageResponse
from app.utils.helper import as_form
from app.utils.file_validation import (
    validate_single_file_size,
)

router = APIRouter()

@router.get("/", response_model=List[DocumentResponse])
async def get_documents(db: Session = Depends(get_db)):
    docs = document_service.get_documents(db)
    return [DocumentResponse.model_validate(d) for d in docs]

@router.get("/session/{session_id}", response_model=List[DocumentResponse])
async def get_documents_by_session(session_id: str, db: Session = Depends(get_db)):
    docs = document_service.get_documents_by_session(db, session_id)
    return [DocumentResponse.model_validate(d) for d in docs]

@router.post("/file", response_model=DocumentResponse)
async def process_file(
    request: FileParseRequest = Depends(as_form(FileParseRequest)),
    db: Session = Depends(get_db)
):
    validate_single_file_size(request.file)
    document = await document_process_service.process_file(db, request.file, request.session_id)
    return DocumentResponse.model_validate(document)

@router.post("/url", response_model=DocumentResponse)
async def process_url(
    request: UrlParseRequest = Depends(as_form(UrlParseRequest)), 
    db: Session = Depends(get_db)
):
    document = await document_process_service.process_url(db, request.url, request.session_id)
    return DocumentResponse.model_validate(document)

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str, db: Session = Depends(get_db)):
    doc = document_service.get_document(db, document_id)
    if not doc:
        raise HTTPException(
            status_code=404, 
            detail=MessageResponse.create(
                translation_key="documentNotFound",
                message="Document not found"
            ).model_dump()
        )
    return DocumentResponse.model_validate(doc)

@router.delete("/{document_id}", response_model=MessageResponse)
async def delete_document(document_id: str, db: Session = Depends(get_db)):
    document_service.delete_document(db, document_id)
    return MessageResponse(message="Document deleted successfully")

@router.put("/{document_id}/rename", response_model=DocumentResponse)
async def rename_document(
    document_id: str, 
    new_filename: str = Form(...),
    db: Session = Depends(get_db)
):
    document = document_service.rename_document(db, document_id, new_filename)
    return DocumentResponse.model_validate(document)
        