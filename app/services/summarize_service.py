import uuid
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models import DocumentSummary
from app.services.text_processor import chunk_service
import os
import traceback
from app.config import settings
import logging

logger = logging.getLogger(__name__)

def create_summary(db: Session, document_id: str, target_chunks: int = 5):
    try:
        existing_summary = db.query(DocumentSummary).filter(
            DocumentSummary.document_id == document_id
        ).first()
        
        if existing_summary:
            return existing_summary
        
        content_file_path = os.path.join(settings.content_files_dir, f"{document_id}.txt")
        
        if not os.path.exists(content_file_path):
            raise HTTPException(status_code=404, detail="Document content file not found")
        
        with open(content_file_path, 'r', encoding='utf-8') as f:
            text_content = f.read()

        result = chunk_service.process_text(text_content, target_chunks)

        summary_id = str(uuid.uuid4())
        summary = DocumentSummary(
            id=summary_id,
            document_id=document_id,
            original_word_count=result["original_word_count"],
            num_chunks=result["num_chunks"],
            chunk_summaries=result["chunk_summaries"],
            global_summary=result["global_summary"]
        )
        
        db.add(summary)
        db.commit()
        db.refresh(summary)
    
        logger.info(f"Created summary {summary_id} for document {document_id}")
        
        return summary
        
    except Exception as e:
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

def get_summary(db: Session, summary_id: str):
    return db.query(DocumentSummary).filter(DocumentSummary.id == summary_id).first()

def get_summary_by_document(db: Session, document_id: str):
    return db.query(DocumentSummary).filter(DocumentSummary.document_id == document_id).first()