import uuid
import os
import traceback
import logging
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_
from fastapi import HTTPException
from app.models import Document, Session as SessionModel, Question, Flashcard
from app.processors.content_processor import content_processor
from app.processors.vector_processor import vector_processor
from app.config import settings, current_date_time
from app.schemas.document import FileParseRequest, SessionCreateRequest, SessionUpdateRequest, UrlParseRequest

logger = logging.getLogger(__name__)

class DocumentService:
    def __init__(self):
        self.content_processor = content_processor
        self.vector_processor = vector_processor

    def get_sessions(self, db: Session):
        return db.query(SessionModel).all()

    def create_session(self, db: Session, request: SessionCreateRequest) -> SessionModel:
        try:
            session = SessionModel(
                user_id=request.user_id, 
                name=request.name, 
                description=request.description
            )
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
            session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
                
            if request.name is not None:
                session.name = request.name
            if request.description is not None:
                session.description = request.description
            session.updated_at = current_date_time()
            
            db.commit()
            return session
        except Exception as e:
            db.rollback()
            logger.error(f"Session update failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def delete_session(self, db: Session, session_id: str):
        try:
            session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            # Delete related documents and files
            documents = db.query(Document).filter(Document.session_id == session_id).all()
            for doc in documents:
                self._cleanup_document_files(doc)

            # Delete related data
            db.query(Question).filter(Question.session_id == session_id).delete()
            db.query(Flashcard).filter(Flashcard.session_id == session_id).delete()
            db.query(Document).filter(Document.session_id == session_id).delete()
            db.delete(session)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Session deletion failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def get_document(self, db: Session, document_id: str) -> Optional[Document]:
        return db.query(Document).filter(Document.id == document_id).first()

    def get_documents(self, db: Session):
        return db.query(Document).all()
    def get_documents_by_session(self, db: Session, session_id: str):
        return db.query(Document).filter(
            and_(
                Document.session_id == session_id,
                Document.processing_status == "completed"
            )
        ).all()

    def parse_document(self, db: Session, request: FileParseRequest) -> Document:
        allowed_types = {
            'application/pdf': 'pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
            'image/jpeg': 'image', 'image/png': 'image', 'image/gif': 'image',
            'image/bmp': 'image', 'image/tiff': 'image'
        }
        
        if request.file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        file_type = allowed_types[request.file.content_type]
        document_id = str(uuid.uuid4())
        temp_file_path = None

        try:
            temp_file_path = self.content_processor.save_temp_file(request.file)
            
            if file_type in ['pdf', 'docx']:
                raw_text = self.content_processor.process_pdf_docx(temp_file_path)
            elif file_type == 'image':
                raw_text = self.content_processor.process_image(temp_file_path)
            else:
                raise HTTPException(status_code=400, detail="Unsupported file type")

            source_file_path = self.content_processor.save_source_file(request.file, document_id)
            content_file_path = self.content_processor.save_content_to_file(raw_text, document_id)

            document = Document(
                id=document_id,
                filename=request.file.filename,
                file_type=file_type,
                source_type="upload",
                content_file_path=content_file_path,
                source_file_path=source_file_path,
                file_size=request.file.size,
                processing_status="processing",
                text_length=len(raw_text),
                session_id=request.session_id
            )
            
            db.add(document)
            db.commit()
            db.refresh(document)

            # Create embeddings
            try:
                chunks = self.vector_processor.chunk_and_embed_document(db, document_id, raw_text)
                document.processing_status = "completed"
                db.commit()
                self._increment_session_documents(db, request.session_id)
                logger.info(f"Created {len(chunks)} chunks for document {document_id}")
            except Exception as e:
                logger.error(f"Embedding failed for {document_id}: {e}")
                self._delete_document(db, document)
                self._decrement_session_documents(db, request.session_id)
                raise HTTPException(status_code=500, detail="Embedding failed")

            return document

        except Exception as e:
            db.rollback()
            logger.error(f"Document processing failed: {e}")
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except:
                    pass

    def parse_audio_video(self, db: Session, request: FileParseRequest) -> Document:
        allowed_types = {
            'audio/mpeg': 'audio', 'audio/wav': 'audio', 'audio/mp3': 'audio',
            'video/mp4': 'video', 'video/avi': 'video', 'video/quicktime': 'video'
        }
        
        if request.file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Unsupported audio/video file type")

        file_type = allowed_types[request.file.content_type]
        document_id = str(uuid.uuid4())
        temp_file_path = None

        try:
            temp_file_path = self.content_processor.save_temp_file(request.file)
            raw_text = self.content_processor.process_audio_video(temp_file_path)
            
            source_file_path = self.content_processor.save_source_file(request.file, document_id)
            content_file_path = self.content_processor.save_content_to_file(raw_text, document_id)

            document = Document(
                id=document_id,
                filename=request.file.filename,
                file_type=file_type,
                source_type="upload",
                content_file_path=content_file_path,
                source_file_path=source_file_path,
                file_size=request.file.size,
                processing_status="processing",
                text_length=len(raw_text),
                session_id=request.session_id
            )

            db.add(document)
            db.commit()
            db.refresh(document)

            try:
                chunks = self.vector_processor.chunk_and_embed_document(db, document_id, raw_text)
                document.processing_status = "completed"
                db.commit()
                self._increment_session_documents(db, request.session_id)
                logger.info(f"Created {len(chunks)} chunks for audio/video document {document_id}")
            except Exception as e:
                logger.error(f"Embedding failed for {document_id}: {e}")
                self._delete_document(db, document)
                self._decrement_session_documents(db, request.session_id)
                raise HTTPException(status_code=500, detail="Embedding failed")

            return document

        except Exception as e:
            db.rollback()
            logger.error(f"Audio/video processing failed: {e}")
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except:
                    pass

    def parse_web_url(self, db: Session, request: UrlParseRequest) -> Document:
        document_id = str(uuid.uuid4())

        try:
            raw_text = self.content_processor.process_web_url(request.url)
            content_file_path = self.content_processor.save_content_to_file(raw_text, document_id)

            document = Document(
                id=document_id,
                filename=request.url,
                file_type="web",
                source_type="url",
                content_file_path=content_file_path,
                processing_status="processing",
                text_length=len(raw_text),
                session_id=request.session_id
            )

            db.add(document)
            db.commit()
            db.refresh(document)

            # Create embeddings
            try:
                chunks = self.vector_processor.chunk_and_embed_document(db, document_id, raw_text)
                document.processing_status = "completed"
                db.commit()
                self._increment_session_documents(db, request.session_id)
                logger.info(f"Created {len(chunks)} chunks for web document {document_id}")
            except Exception as e:
                logger.error(f"Embedding failed for {document_id}: {e}")
                self._delete_document(db, document)
                self._decrement_session_documents(db, request.session_id)
                raise HTTPException(status_code=500, detail="Embedding failed")

            return document

        except Exception as e:
            db.rollback()
            logger.error(f"Web URL processing failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def parse_youtube(self, db: Session, request: UrlParseRequest) -> Document:
        document_id = str(uuid.uuid4())
        audio_path = None

        try:
            audio_path = self.content_processor.download_youtube_video(request.url)
            raw_text = self.content_processor.process_audio_video(audio_path)
            content_file_path = self.content_processor.save_content_to_file(raw_text, document_id)
            source_file_path = self.content_processor.save_local_file(audio_path, document_id)

            document = Document(
                id=document_id,
                filename=request.url,
                file_type="youtube",
                source_type="youtube",
                content_file_path=content_file_path,
                source_file_path=source_file_path,
                processing_status="processing",
                text_length=len(raw_text),
                session_id=request.session_id
            )

            db.add(document)
            db.commit()
            db.refresh(document)

            try:
                chunks = self.vector_processor.chunk_and_embed_document(db, document_id, raw_text)
                document.processing_status = "completed"
                db.commit()
                self._increment_session_documents(db, request.session_id)
                logger.info(f"Created {len(chunks)} chunks for YouTube document {document_id}")
            except Exception as e:
                logger.error(f"Embedding failed for {document_id}: {e}")
                self._delete_document(db, document)
                self._decrement_session_documents(db, request.session_id)
                raise HTTPException(status_code=500, detail="Embedding failed")

            return document

        except Exception as e:
            db.rollback()
            logger.error(f"YouTube processing failed: {e}")
            if audio_path and os.path.exists(audio_path):
                self._cleanup_audio_directory(audio_path)
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            if audio_path and os.path.exists(audio_path):
                self._cleanup_audio_directory(audio_path)

    def _delete_document(self, db: Session, document: Document):
        try:
            self._cleanup_document_files(document)
            db.delete(document)
            db.commit()
            logger.info(f"Deleted document {document.id}")
        except Exception as e:
            logger.error(f"Error deleting document {document.id}: {e}")
            db.rollback()

    def _cleanup_document_files(self, document: Document):
        try:
            if document.source_file_path and os.path.exists(document.source_file_path):
                os.remove(document.source_file_path)
            if document.content_file_path and os.path.exists(document.content_file_path):
                os.remove(document.content_file_path)
        except Exception as e:
            logger.warning(f"File cleanup failed for document {document.id}: {e}")

    def _cleanup_audio_directory(self, audio_path: str):
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
            
            audio_dir = os.path.dirname(audio_path)
            if os.path.exists(audio_dir) and not os.listdir(audio_dir):
                os.rmdir(audio_dir)
        except Exception as e:
            logger.warning(f"Failed to cleanup audio directory: {e}")

    def _increment_session_documents(self, db: Session, session_id: str):
        try:
            session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
            if session:
                session.total_documents += 1
                db.commit()
        except Exception as e:
            logger.error(f"Failed to increment total_documents for session {session_id}: {e}")

    def _decrement_session_documents(self, db: Session, session_id: str):
        try:
            session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
            if session and session.total_documents > 0:
                session.total_documents -= 1
                db.commit()
        except Exception as e:
            logger.error(f"Failed to decrement total_documents for session {session_id}: {e}")

document_service = DocumentService()