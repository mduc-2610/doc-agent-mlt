from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import uuid

class SummaryResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    summary_content: str
    document_count: int
    total_word_count: int
    summary_word_count: int
    generation_model: str
    summary_file_path: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class SummaryGenerationRequest(BaseModel):
    user_id: str
    regenerate: bool = False  