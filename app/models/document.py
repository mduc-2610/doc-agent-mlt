from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
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
    source_type = Column(String(50), nullable=False)
    processing_status = Column(String(50), default="processing")
    content_file_path = Column(String(500))
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
    embedding = Column(Vector(1024))  
    extra_metadata = Column(JSON)
    created_at = Column(DateTime, default=current_date_time)
    
    document = relationship("Document", backref="chunks")

class DocumentSummary(Base):
    __tablename__ = "document_summaries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), nullable=False)
    summary_file_path = Column(String(500))
    model_used = Column(String(100))
    original_word_count = Column(Integer, nullable=False)
    summary_word_count = Column(Integer)
    created_at = Column(DateTime, default=current_date_time)