from pydantic import BaseModel
from fastapi import UploadFile, File
from datetime import datetime
from typing import List, Optional
import uuid

class SessionResponse(BaseModel):
    id: uuid.UUID
    user_id: str
    name: str
    description: str | None
    document_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class DocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    file_type: str
    file_size: Optional[int] = None  
    source_type: Optional[str] = None
    processing_status: str
    content_file_path: Optional[str] = None
    text_length: int
    session_id: Optional[uuid.UUID] = None  
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SessionDetailResponse(SessionResponse):
    pass
class SessionCreateRequest(BaseModel):
    user_id: str
    name: str
    description: Optional[str] = ""


class SessionUpdateRequest(BaseModel):
    name: str
    description: Optional[str] = ""

class SessionUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class UrlParseRequest(BaseModel):
    url: str
    session_id: Optional[str] = None

class FileParseRequest(BaseModel):
    file: UploadFile = File(...)
    session_id: Optional[str] = None

class MessageResponse(BaseModel):
    message: str