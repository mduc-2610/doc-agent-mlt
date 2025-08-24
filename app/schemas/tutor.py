from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

class TutorSessionCreate(BaseModel):
    session_id: str
    user_id: str
    tutor_type: str = Field(..., description="Type: 'learning', 'flashcard', 'explanation'")
    current_context: Optional[str] = None

class TutorInteractionCreate(BaseModel):
    tutor_session_id: str
    user_input: str
    interaction_type: str = Field(..., description="Type: 'question', 'answer', 'explanation', 'feedback'")
    related_question_id: Optional[str] = None
    related_flashcard_id: Optional[str] = None

class TutorResponse(BaseModel):
    response: str
    confidence_score: Optional[float] = None
    context_used: Optional[str] = None
    suggestions: Optional[List[str]] = None
    related_resources: Optional[List[Dict[str, Any]]] = None

class TutorInteractionResponse(BaseModel):
    id: uuid.UUID
    interaction_type: str
    user_input: Optional[str]
    tutor_response: str
    confidence_score: Optional[float]
    context_used: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True

class TutorSessionResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    user_id: str
    tutor_type: str
    current_context: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    interactions: List[TutorInteractionResponse] = []
    
    class Config:
        from_attributes = True

class LearningProgressResponse(BaseModel):
    id: uuid.UUID
    user_id: str
    session_id: uuid.UUID
    topic: Optional[str]
    total_questions_answered: int
    correct_answers: int
    total_flashcards_reviewed: int
    flashcards_mastered: int
    concepts_explained: int
    study_time_minutes: int
    mastery_level: float
    last_activity: datetime
    
    class Config:
        from_attributes = True

class ExplainConceptRequest(BaseModel):
    user_id: str
    session_id: str
    concept: str
    difficulty_level: Optional[str] = "intermediate"  # beginner, intermediate, advanced
    learning_style: Optional[str] = "comprehensive"  # brief, comprehensive, detailed

class FlashcardStudyRequest(BaseModel):
    user_id: str
    session_id: str
    flashcard_id: Optional[str] = None
    difficulty_filter: Optional[str] = None
    topic_filter: Optional[str] = None

class FlashcardStudyResponse(BaseModel):
    flashcard_id: uuid.UUID
    question: str
    show_answer: bool = False
    answer: Optional[str] = None
    explanation: Optional[str] = None
    progress_info: Optional[Dict[str, Any]] = None

class QuestionPracticeRequest(BaseModel):
    user_id: str
    session_id: str
    question_id: Optional[str] = None
    difficulty_filter: Optional[str] = None
    topic_filter: Optional[str] = None

class QuestionPracticeResponse(BaseModel):
    question_id: uuid.UUID
    question: str
    question_type: str
    options: Optional[List[str]] = None
    user_answer: Optional[str] = None
    is_correct: Optional[bool] = None
    explanation: Optional[str] = None
    progress_info: Optional[Dict[str, Any]] = None

class UserQuestionRequest(BaseModel):
    user_id: str
    session_id: str
    question: str
    context_hint: Optional[str] = None  # Optional hint about what context to focus on

class LearningPathRequest(BaseModel):
    user_id: str
    session_id: str
    learning_goals: List[str]
    current_knowledge_level: Optional[str] = "beginner"
    preferred_learning_style: Optional[str] = "mixed"
