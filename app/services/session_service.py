import logging
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models import Session as SessionModel, Document, Question, Flashcard, QuestionAnswer
from app.config import current_date_time
from app.schemas.session import SessionCreateRequest, SessionUpdateRequest
from app.storages import get_storage_provider

logger = logging.getLogger(__name__)

class SessionService:
    def get_sessions(self, db: Session):
        return db.query(SessionModel).all()

    def create_session(self, db: Session, request: SessionCreateRequest) -> SessionModel:
        try:
            session = SessionModel(user_id=request.user_id, name=request.name, description=request.description)
            db.add(session)
            db.commit()
            db.refresh(session)
            return session
        except Exception as e:
            db.rollback()
            logger.error(f"Session creation failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def get_session(self, db: Session, session_id: str) -> Optional[SessionModel]:
        return db.query(SessionModel).filter(SessionModel.id == session_id).first()

    def get_user_sessions(self, db: Session, user_id: str):
        return db.query(SessionModel).filter(SessionModel.user_id == user_id).all()

    def update_session(self, db: Session, session_id: str, request: SessionUpdateRequest):
        try:
            session = self.get_session(db, session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
            
            if request.name is not None: session.name = request.name
            if request.description is not None: session.description = request.description
            session.updated_at = current_date_time()
            
            db.commit()
            return session
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Session update failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def delete_session(self, db: Session, session_id: str):
        try:
            session = self.get_session(db, session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
            
            for doc in db.query(Document).filter(Document.session_id == session_id).all():
                self._cleanup_document_files(doc)
                
            
            db.query(QuestionAnswer).filter(QuestionAnswer.question_id.in_(
                db.query(Question.id).filter(Question.session_id == session_id)
            )).delete(synchronize_session=False)
            
            for model in [Question, Flashcard, Document]:
                db.query(model).filter(model.session_id == session_id).delete(synchronize_session=False)
            
            db.delete(session)
            db.commit()
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Session deletion failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def _cleanup_document_files(self, document: Document):
        try:
            storage = get_storage_provider(document.storage_provider or "local")
            deleted_count = storage.delete_files_by_pattern(document.id, case_sensitive=True)
            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} files for session {document.id} from {storage}: {e}")
        except Exception as e:
            logger.warning(f"Failed to cleanup files for session {document.id} from {storage}: {e}")

        
    def update_session_documents(self, db: Session, session_id: str, increment: bool = True):
        try:
            session = self.get_session(db, session_id)
            if session:
                session.total_documents += 1 if increment else (-1 if session.total_documents > 0 else 0)
                db.commit()
        except Exception as e:
            logger.error(f"Failed to update total_documents for session {session_id}: {e}")

session_service = SessionService()
