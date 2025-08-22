from app.models.session import Session
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
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
    source_type = Column(String(50), nullable=False)
    processing_status = Column(String(50), default="processing")
    content_file_path = Column(String(500))
    source_file_path = Column(String(500))
    text_length = Column(Integer, default=0)
    session_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=current_date_time)
    updated_at = Column(DateTime, default=current_date_time, onupdate=current_date_time)

class DocumentSummary(Base):
    __tablename__ = "document_summaries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, unique=True)
    summary_content = Column(Text, nullable=False)
    document_count = Column(Integer, nullable=False, default=0)
    total_word_count = Column(Integer, nullable=False, default=0)
    summary_word_count = Column(Integer, nullable=False, default=0)
    generation_model = Column(String(100), nullable=False)
    summary_file_path = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=current_date_time)
    updated_at = Column(DateTime, default=current_date_time, onupdate=current_date_time)

    document = relationship("Document", backref="summary")

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

@event.listens_for(Document, "after_insert")
def after_document_insert(mapper, connection, target: Document):
    connection.execute(
        Session.__table__.update()
        .where(Session.id == target.session_id)
        .values(total_documents=Session.total_documents + 1)
    )

@event.listens_for(Document, "after_delete")
def after_document_delete(mapper, connection, target: Document):
    connection.execute(
        Session.__table__.update()
        .where(Session.id == target.session_id)
        .values(total_documents=Session.total_documents - 1)
    )