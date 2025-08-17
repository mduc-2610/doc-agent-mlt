from pydantic import BaseModel
from fastapi import UploadFile, File
from typing import Optional, List
from datetime import datetime
import uuid

class FlashcardResponse(BaseModel):
    id: uuid.UUID
    topic: Optional[str] = None
    card_type: str
    question: str
    answer: str
    explanation: Optional[str] = None
    document_id: Optional[uuid.UUID] = None
    session_id: Optional[uuid.UUID] = None
    user_id: str
    created_at: datetime

    source_context: Optional[str] = None
    generation_model: Optional[str] = None
    validation_score: Optional[float] = None

    class Config:
        from_attributes = True

class QuestionAnswerResponse(BaseModel):
    id: uuid.UUID
    content: str
    is_correct: bool = False
    explanation: Optional[str] = None

    class Config:
        from_attributes = True

class QuestionResponse(BaseModel):
    id: uuid.UUID
    topic: Optional[str] = None
    content: str
    type: str
    difficulty_level: Optional[str] = None
    correct_answer: str
    explanation: Optional[str] = None
    document_id: Optional[uuid.UUID] = None
    session_id: Optional[uuid.UUID] = None
    user_id: str
    created_at: datetime
    question_answers: List[QuestionAnswerResponse] = []

    source_context: Optional[str] = None
    generation_model: Optional[str] = None
    validation_score: Optional[float] = None
    
    class Config:
        from_attributes = True

class DocumentUploadBase(BaseModel):
    user_id: str
    session_id: Optional[str] = None
    question_count: int = 15
    flashcard_count: int = 15
    topic: Optional[str] = "General content analysis"

class DocumentFileUploadRequest(DocumentUploadBase):
    file: UploadFile = File(...)

class DocumentUrlUploadRequest(DocumentUploadBase):
    url: str
    
class QuestionGenerationRequest(BaseModel):
    topic: Optional[str] = "General content analysis"
    document_ids: List[str]
    session_id: Optional[str] = None
    user_id: str
    quiz_count: int = 15
    flashcard_count: int = 15

class ReviewRequest(BaseModel):
    generation_id: str
    action: str
    selected_question_ids: Optional[List[str]] = None
    reviewer_notes: Optional[str] = None
