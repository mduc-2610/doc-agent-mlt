from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer, Boolean, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.config import settings, current_date_time

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=current_date_time)
    updated_at = Column(DateTime, default=current_date_time, onupdate=current_date_time)

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)
    source_type = Column(String(50), nullable=False)
    content_file_path = Column(String(500))
    file_size = Column(Integer)
    processing_status = Column(String(50), default="processing")
    text_length = Column(Integer, default=0)
    session_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=current_date_time)
    updated_at = Column(DateTime, default=current_date_time, onupdate=current_date_time)

class DocumentSummary(Base):
    __tablename__ = "document_summaries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), nullable=False)
    original_word_count = Column(Integer, nullable=False)
    num_chunks = Column(Integer, nullable=False)
    chunk_summaries = Column(JSON, nullable=False)
    global_summary = Column(Text, nullable=False)
    created_at = Column(DateTime, default=current_date_time)

class Question(Base):
    __tablename__ = "questions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    type = Column(String(50), nullable=False)  
    difficulty_level = Column(String(50))  
    correct_answer = Column(Text, nullable=False)
    document_id = Column(UUID(as_uuid=True))
    session_id = Column(UUID(as_uuid=True))
    user_id = Column(String(255))
    explanation = Column(Text)
    created_at = Column(DateTime, default=current_date_time)

    question_answers = relationship("QuestionAnswer", back_populates="question", cascade="all, delete-orphan")

class QuestionAnswer(Base):
    __tablename__ = "question_answers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    is_correct = Column(Boolean, default=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False)
    
    question = relationship("Question", back_populates="question_answers")

class Flashcard(Base):
    __tablename__ = "flashcards"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_type = Column(String(50), nullable=False) 
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    explanation = Column(Text)
    document_id = Column(UUID(as_uuid=True))
    session_id = Column(UUID(as_uuid=True))
    user_id = Column(String(255))
    created_at = Column(DateTime, default=current_date_time)