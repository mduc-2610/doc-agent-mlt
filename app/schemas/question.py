from pydantic import BaseModel, Field
from fastapi import UploadFile, File
from typing import Optional, List
from datetime import datetime
import uuid
from app.config import settings

class FlashcardResponse(BaseModel):
    id: uuid.UUID
    topic: Optional[str] = None
    card_type: str
    question: str
    answer: str
    explanation: Optional[str] = None
    document_id: Optional[uuid.UUID] = None
    session_id: Optional[uuid.UUID] = None
    created_at: datetime

    source_context: Optional[str] = None
    generation_model: Optional[str] = None

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
    created_at: datetime
    question_answers: List[QuestionAnswerResponse] = []

    source_context: Optional[str] = None
    generation_model: Optional[str] = None
    
    class Config:
        from_attributes = True

    
class QuestionGenerationRequest(BaseModel):
    topic: Optional[str] = Field(
        default="General content analysis",
        max_length=100,
        description="Topic for question generation (max 100 characters)"
    )
    document_ids: List[str]
    session_id: Optional[str] = None
    quiz_count: int = Field(
        default=15, 
        ge=1, 
        le=settings.generation.max_questions_per_request, 
        description=f"Number of quiz questions to generate (1-{settings.generation.max_questions_per_request})"
    )
    flashcard_count: int = Field(
        default=15, 
        ge=1, 
        le=settings.generation.max_flashcards_per_request, 
        description=f"Number of flashcards to generate (1-{settings.generation.max_flashcards_per_request})"
    )
    
class QuestionUpdateRequest(BaseModel):
    content: str
    type: str
    correct_answer: str
    explanation: Optional[str] = None
    topic: Optional[str] = Field(None, max_length=100, description="Topic (max 100 characters)")
    difficulty_level: Optional[str] = None
    question_answers: Optional[List[dict]] = None

class FlashcardUpdateRequest(BaseModel):
    question: str
    answer: str
    card_type: str
    explanation: Optional[str] = None
    topic: Optional[str] = Field(None, max_length=100, description="Topic (max 100 characters)")

class QuestionCreateRequest(BaseModel):
    content: str
    type: str
    correct_answer: str
    explanation: Optional[str] = None
    topic: Optional[str] = Field(None, max_length=100, description="Topic (max 100 characters)")
    difficulty_level: Optional[str] = None
    session_id: str
    question_answers: Optional[List[dict]] = None

class FlashcardCreateRequest(BaseModel):
    question: str
    answer: str
    card_type: str
    explanation: Optional[str] = None
    topic: Optional[str] = Field(None, max_length=100, description="Topic (max 100 characters)")
    session_id: str
