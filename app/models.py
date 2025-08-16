from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer, Boolean, ForeignKey, JSON, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
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

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=False)
    # Vector embedding column for pgvector
    embedding = Column(Vector(1024))  # BGE-large-v1.5 produces 1024-dimensional vectors
    extra_metadata = Column(JSON)
    created_at = Column(DateTime, default=current_date_time)
    
    document = relationship("Document", backref="chunks")

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
    topic = Column(String(255))  # New: for topic-based generation
    correct_answer = Column(Text, nullable=False)
    document_id = Column(UUID(as_uuid=True))
    session_id = Column(UUID(as_uuid=True))
    user_id = Column(String(255))
    explanation = Column(Text)
    source_context = Column(Text)  # New: context used for generation
    generation_model = Column(String(100))  # New: track which model generated this
    validation_score = Column(Float)  # New: quality score
    human_validated = Column(Boolean, default=False)  # New: human review flag
    created_at = Column(DateTime, default=current_date_time)

    question_answers = relationship("QuestionAnswer", back_populates="question", cascade="all, delete-orphan")

class QuestionAnswer(Base):
    __tablename__ = "question_answers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    is_correct = Column(Boolean, default=False)
    explanation = Column(Text)  # New: explanation for why this answer is correct/incorrect
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False)
    
    question = relationship("Question", back_populates="question_answers")

class Flashcard(Base):
    __tablename__ = "flashcards"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_type = Column(String(50), nullable=False) 
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    explanation = Column(Text)
    topic = Column(String(255))  # New: for topic-based generation
    source_context = Column(Text)  # New: context used for generation
    generation_model = Column(String(100))  # New: track which model generated this
    validation_score = Column(Float)  # New: quality score
    human_validated = Column(Boolean, default=False)  # New: human review flag
    document_id = Column(UUID(as_uuid=True))
    session_id = Column(UUID(as_uuid=True))
    user_id = Column(String(255))
    created_at = Column(DateTime, default=current_date_time)

class QuestionGeneration(Base):
    __tablename__ = "question_generations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_input = Column(Text, nullable=False)  # e.g., "Topic: Delta Lake"
    context_chunks = Column(JSON, nullable=False)  # Retrieved context
    generation_parameters = Column(JSON)  # Model params, retry count, etc.
    output_questions = Column(JSON)  # Generated questions before validation
    final_questions = Column(JSON)  # Validated and approved questions
    model_version = Column(String(100))
    generation_status = Column(String(50), default="processing")  # processing, completed, failed
    retry_count = Column(Integer, default=0)
    human_review_status = Column(String(50), default="pending")  # pending, approved, rejected
    created_at = Column(DateTime, default=current_date_time)
    updated_at = Column(DateTime, default=current_date_time, onupdate=current_date_time)