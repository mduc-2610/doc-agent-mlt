from app.models.session import Session
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, backref
from sqlalchemy import event
from pgvector.sqlalchemy import Vector
import uuid
from app.config import current_date_time
from .base import Base


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)
    file_size = Column(Integer)
    source_name = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False)
    processing_status = Column(String(50), default="processing")
    content_file_path = Column(String(500))
    source_file_path = Column(String(500))
    text_length = Column(Integer, default=0)
    extra_metadata = Column(JSON)  # Store document metadata including media files
    storage_provider = Column(String(50), default="local")  # local, minio, etc.
    storage_bucket = Column(String(100))  # bucket name for cloud providers
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=current_date_time)
    updated_at = Column(DateTime, default=current_date_time, onupdate=current_date_time)

    session = relationship("Session", back_populates="documents")
    summary = relationship("DocumentSummary", back_populates="document", uselist=False, cascade="all, delete-orphan")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentSummary(Base):
    __tablename__ = "document_summaries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    summary_content = Column(Text, nullable=False)
    document_count = Column(Integer, nullable=False, default=0)
    total_word_count = Column(Integer, nullable=False, default=0)
    summary_word_count = Column(Integer, nullable=False, default=0)
    generation_model = Column(String(100), nullable=False)
    summary_file_path = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=current_date_time)
    updated_at = Column(DateTime, default=current_date_time, onupdate=current_date_time)

    document = relationship("Document", back_populates="summary")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=False)
    embedding = Column(Vector(384))  # Updated for multilingual MiniLM model  
    extra_metadata = Column(JSON)
    created_at = Column(DateTime, default=current_date_time)

    document = relationship("Document", back_populates="chunks")

Session.documents = relationship("Document", back_populates="session", cascade="all, delete-orphan")
