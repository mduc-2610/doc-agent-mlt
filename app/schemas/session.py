from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import uuid

class SessionResponse(BaseModel):
    id: uuid.UUID
    user_id: str
    name: str
    description: str | None
    total_documents: int
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
    name: Optional[str] = None
    description: Optional[str] = None
