from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey, JSON, Float, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.config import current_date_time
from .base import Base

class TutorSession(Base):
    __tablename__ = "tutor_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), nullable=False)  # Links to main session
    user_id = Column(String(255), nullable=False)
    tutor_type = Column(String(50), nullable=False)  # 'learning', 'flashcard', 'explanation'
    current_context = Column(Text)  # Current learning context
    progress_data = Column(JSON)  # JSON data for tracking progress
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=current_date_time)
    updated_at = Column(DateTime, default=current_date_time, onupdate=current_date_time)
    
    # Relationship to interactions
    interactions = relationship("TutorInteraction", back_populates="tutor_session", cascade="all, delete-orphan")

class TutorInteraction(Base):
    __tablename__ = "tutor_interactions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tutor_session_id = Column(UUID(as_uuid=True), ForeignKey("tutor_sessions.id"), nullable=False)
    interaction_type = Column(String(50), nullable=False)  # 'question', 'answer', 'explanation', 'feedback'
    user_input = Column(Text)  # User's input/question
    tutor_response = Column(Text, nullable=False)  # AI tutor's response
    context_used = Column(Text)  # Context from documents used for response
    related_question_id = Column(UUID(as_uuid=True))  # Link to specific question if applicable
    related_flashcard_id = Column(UUID(as_uuid=True))  # Link to specific flashcard if applicable
    confidence_score = Column(Float)  # Confidence in the response
    user_feedback = Column(String(50))  # 'helpful', 'not_helpful', 'partially_helpful'
    extra_metadata = Column(JSON)  # Additional metadata
    created_at = Column(DateTime, default=current_date_time)
    
    # Relationship
    tutor_session = relationship("TutorSession", back_populates="interactions")

class LearningProgress(Base):
    __tablename__ = "learning_progress"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False)
    session_id = Column(UUID(as_uuid=True), nullable=False)
    topic = Column(String(255))
    total_questions_answered = Column(Integer, default=0)
    correct_answers = Column(Integer, default=0)
    total_flashcards_reviewed = Column(Integer, default=0)
    flashcards_mastered = Column(Integer, default=0)
    concepts_explained = Column(Integer, default=0)
    study_time_minutes = Column(Integer, default=0)
    last_activity = Column(DateTime, default=current_date_time)
    mastery_level = Column(Float, default=0.0)  # 0.0 to 1.0
    created_at = Column(DateTime, default=current_date_time)
    updated_at = Column(DateTime, default=current_date_time, onupdate=current_date_time)
