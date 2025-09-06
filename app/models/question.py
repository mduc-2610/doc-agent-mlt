from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey, JSON, Float, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.config import current_date_time
from .base import Base

class Question(Base):
    __tablename__ = "questions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    type = Column(String(50), nullable=False)  
    difficulty_level = Column(String(50))
    topic = Column(String(255))
    correct_answer = Column(Text, nullable=False)
    session_id = Column(UUID(as_uuid=True))
    explanation = Column(Text)
    source_context = Column(Text)
    generation_model = Column(String(100))
    created_at = Column(DateTime, default=current_date_time)

    question_answers = relationship("QuestionAnswer", back_populates="question", cascade="all, delete-orphan")

class QuestionAnswer(Base):
    __tablename__ = "question_answers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    is_correct = Column(Boolean, default=False)
    explanation = Column(Text)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False)
    
    question = relationship("Question", back_populates="question_answers")

class Flashcard(Base):
    __tablename__ = "flashcards"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_type = Column(String(50), nullable=False) 
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    explanation = Column(Text)
    topic = Column(String(255))
    source_context = Column(Text)
    generation_model = Column(String(100))
    session_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=current_date_time)
