from pydantic import BaseModel
from fastapi import UploadFile, File
from datetime import datetime
from typing import Optional
import uuid

class UrlParseRequest(BaseModel):
    url: str
    session_id: Optional[str] = None

class FileParseRequest(BaseModel):
    file: UploadFile = File(...)
    session_id: Optional[str] = None

class DocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    source_name: str
    file_type: str
    file_size: Optional[int] = None  
    source_type: Optional[str] = None
    processing_status: str
    content_file_path: Optional[str] = None
    source_file_path: Optional[str] = None
    text_length: int
    extra_metadata: Optional[dict] = None
    storage_provider: Optional[str] = "local"
    storage_bucket: Optional[str] = None
    session_id: Optional[uuid.UUID] = None  
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class DocumentSummaryResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    summary_content: str
    document_count: int
    total_word_count: int
    summary_word_count: int
    summary_file_path: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True