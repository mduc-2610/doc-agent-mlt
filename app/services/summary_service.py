import uuid
import os
import traceback
from typing import Optional, List
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models import Document, SessionSummary, Session as SessionModel
from app.processors.summary_processor import summary_processor
from app.config import current_date_time
import logging

logger = logging.getLogger(__name__)

class SummaryService:
    def __init__(self):
        self.summary_processor = summary_processor

    def get_session_summary(self, db: Session, session_id: str) -> Optional[SessionSummary]:
        """Get existing summary for a session"""
        return db.query(SessionSummary).filter(SessionSummary.session_id == session_id).first()

    def get_session_documents_content(self, db: Session, session_id: str) -> List[str]:
        """Get all document contents for a session"""
        documents = db.query(Document).filter(
            Document.session_id == session_id,
            Document.processing_status == "completed"
        ).all()
        
        documents_content = []
        for doc in documents:
            if doc.content_file_path and os.path.exists(doc.content_file_path):
                try:
                    with open(doc.content_file_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            documents_content.append(content)
                except Exception as e:
                    logger.warning(f"Failed to read document {doc.id}: {e}")
                    continue
        
        return documents_content

    def generate_or_update_summary(self, db: Session, session_id: str, regenerate: bool = False) -> SessionSummary:
        try:
            session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            documents_content = self.get_session_documents_content(db, session_id)
            
            if not documents_content:
                raise HTTPException(status_code=400, detail="No processed documents found in session")

            existing_summary = self.get_session_summary(db, session_id)
            
            total_word_count = sum(len(content.split()) for content in documents_content)
            document_count = len(documents_content)
            
            if existing_summary and not regenerate:
                if existing_summary.document_count == document_count:
                    logger.info(f"Summary for session {session_id} is up to date")
                    return existing_summary
                else:
                    logger.info(f"New documents detected, updating summary for session {session_id}")

            summary_content = self.summary_processor.generate_session_summary(
                documents_content, 
                session.name
            )
            
            summary_word_count = len(summary_content.split())
            
            if existing_summary:
                summary_id = str(existing_summary.id)
                
                if existing_summary.summary_file_path and os.path.exists(existing_summary.summary_file_path):
                    try:
                        os.remove(existing_summary.summary_file_path)
                    except Exception as e:
                        logger.warning(f"Failed to remove old summary file: {e}")
                
                summary_file_path = self.summary_processor.save_summary_to_file(summary_content, summary_id)
                
                existing_summary.summary_content = summary_content
                existing_summary.document_count = document_count
                existing_summary.total_word_count = total_word_count
                existing_summary.summary_word_count = summary_word_count
                existing_summary.generation_model = self.summary_processor.model_name
                existing_summary.summary_file_path = summary_file_path
                existing_summary.updated_at = current_date_time()
                
                db.commit()
                db.refresh(existing_summary)
                
                logger.info(f"Updated summary for session {session_id}")
                logger.info(f"Summary details session {existing_summary}")
                return existing_summary
            
            else:
                # Create new summary
                summary_id = str(uuid.uuid4())
                summary_file_path = self.summary_processor.save_summary_to_file(summary_content, summary_id)
                
                new_summary = SessionSummary(
                    id=summary_id,
                    session_id=session_id,
                    summary_content=summary_content,
                    document_count=document_count,
                    total_word_count=total_word_count,
                    summary_word_count=summary_word_count,
                    generation_model=self.summary_processor.model_name,
                    summary_file_path=summary_file_path,
                    created_at=current_date_time(),
                    updated_at=current_date_time()
                )
                
                db.add(new_summary)
                db.commit()
                db.refresh(new_summary)
                
                logger.info(f"Created new summary for session {session_id}")
                return new_summary

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to generate/update summary for session {session_id}: {e}")
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))

    def delete_session_summary(self, db: Session, session_id: str):
        """Delete summary when session is deleted"""
        try:
            summary = self.get_session_summary(db, session_id)
            if summary:
                # Remove summary file
                if summary.summary_file_path and os.path.exists(summary.summary_file_path):
                    try:
                        os.remove(summary.summary_file_path)
                    except Exception as e:
                        logger.warning(f"Failed to remove summary file: {e}")
                
                # Delete from database
                db.delete(summary)
                db.commit()
                logger.info(f"Deleted summary for session {session_id}")
        
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete summary for session {session_id}: {e}")
            traceback.print_exc()
            raise

summary_service = SummaryService()