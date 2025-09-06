import logging
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_
from fastapi import HTTPException
from app.models import Document
from app.config import current_date_time
from app.storages import get_storage_provider
from app.services.session_service import session_service

logger = logging.getLogger(__name__)

class DocumentService:
    def __init__(self):
        self.storage = get_storage_provider()

    def _handle_db_operation(self, db: Session, operation, error_msg: str):
        try:
            return operation()
        except Exception as e:
            db.rollback()
            logger.error(f"{error_msg}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def get_document(self, db: Session, document_id: str) -> Optional[Document]:
        return db.query(Document).filter(Document.id == document_id).first()

    def get_documents(self, db: Session):
        return db.query(Document).all()

    def get_documents_by_session(self, db: Session, session_id: str):
        return db.query(Document).filter(
            and_(Document.session_id == session_id, Document.processing_status == "completed")
        ).all()

    def delete_document(self, db: Session, document_id: str):
        def delete_operation():
            document = self._get_document_or_404(db, document_id)
            session_id = document.session_id
            
            from app.models.document import DocumentChunk, DocumentSummary
            for model in [DocumentChunk, DocumentSummary]:
                db.query(model).filter(model.document_id == document_id).delete()
            
            self._cleanup_document_files(document)
            db.delete(document)
            db.commit()
            session_service.update_session_documents(db, session_id, False)
            
        return self._handle_db_operation(db, delete_operation, f"Document deletion failed for {document_id}")

    def rename_document(self, db: Session, document_id: str, new_filename: str):
        try:
            document = self._get_document_or_404(db, document_id)
            document.source_name = new_filename
            document.updated_at = current_date_time()
            db.commit()
            db.refresh(document)
            return document
        except Exception as e:
            db.rollback()
            logger.error(f"Document rename failed for {document_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def _get_document_or_404(self, db: Session, document_id: str) -> Document:
        document = self.get_document(db, document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return document

    def _cleanup_document_files(self, document: Document):
        try:
            storage = get_storage_provider(document.storage_provider or "local")
            for file_path in filter(None, [document.source_file_path, document.content_file_path]):
                try:
                    storage.delete_file(file_path)
                except Exception as e:
                    logger.warning(f"File cleanup failed for {file_path}: {e}")
        except Exception as e:
            logger.warning(f"Storage provider initialization failed during cleanup: {e}")

document_service = DocumentService()