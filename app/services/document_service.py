import uuid
import os
import traceback
import logging
from typing import Optional, List, Tuple, Dict, Any
from services_monolithic.app.models.question import Flashcard, Question
from sqlalchemy.orm import Session
from fastapi import HTTPException, UploadFile
from app.models import Document, Session as SessionModel
from app.processors.content_processor import content_processor
from app.processors.vector_processor import vector_processor
from app.config import settings, current_date_time
from app.schemas.document import FileParseRequest, SessionCreateRequest, UrlParseRequest
from app.utils.error_handling import (
    handle_database_errors, 
    validate_input, 
    validate_document_request,
    validate_session_request,
    ErrorCollector,
    safe_execute
)
from app.services.monitoring_service import monitoring_service, MonitoredOperation
from app.database import BatchOperations

logger = logging.getLogger(__name__)

class DocumentService:
    def __init__(self):
        self.content_processor = content_processor
        self.vector_processor = vector_processor

    @handle_database_errors
    def get_sessions(self, db: Session):
        with MonitoredOperation("get_sessions"):
            return db.query(SessionModel).all()

    @handle_database_errors
    @validate_input(validate_session_request)
    def create_session(self, db: Session, request: SessionCreateRequest) -> SessionModel:
        with MonitoredOperation("create_session") as op:
            try:
                op.add_metadata(user_id=request.user_id, name=request.name)
                
                session = SessionModel(user_id=request.user_id, name=request.name, description=request.description)
                db.add(session)
                db.commit()
                db.refresh(session)
                
                op.add_metadata(session_id=str(session.id))
                return session
                
            except Exception as e:
                traceback.print_exc()
                db.rollback()
                raise HTTPException(status_code=500, detail=str(e))

    @handle_database_errors
    def get_session(self, db: Session, session_id: str) -> Optional[SessionModel]:
        with MonitoredOperation("get_session") as op:
            op.add_metadata(session_id=session_id)
            return db.query(SessionModel).filter(SessionModel.id == session_id).first()

    @handle_database_errors
    def get_user_sessions(self, db: Session, user_id: str):
        with MonitoredOperation("get_user_sessions") as op:
            op.add_metadata(user_id=user_id)
            sessions = db.query(SessionModel).filter(SessionModel.user_id == user_id).all()
            op.add_metadata(sessions_found=len(sessions))
            return sessions

    @handle_database_errors
    @validate_input(validate_session_request)
    def update_session(self, db: Session, session_id, request: SessionCreateRequest):
        with MonitoredOperation("update_session") as op:
            try:
                op.add_metadata(session_id=session_id)
                
                session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
                if not session:
                    raise HTTPException(status_code=404, detail="Session not found")
                    
                if request.name is not None:
                    session.name = request.name
                if request.description is not None:
                    session.description = request.description
                session.updated_at = current_date_time()
                
                db.commit()
                op.add_metadata(update_success=True)
                return session
                
            except Exception as e:
                traceback.print_exc()
                db.rollback()
                raise HTTPException(status_code=500, detail=str(e))

    @handle_database_errors
    def delete_session(self, db: Session, session_id: str):
        with MonitoredOperation("delete_session") as op:
            try:
                op.add_metadata(session_id=session_id)
                
                session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
                if not session:
                    raise HTTPException(status_code=404, detail="Session not found")

                documents = db.query(Document).filter(Document.session_id == session_id).all()
                
                error_collector = ErrorCollector()
                for doc in documents:
                    if doc.content_file_path and os.path.exists(doc.content_file_path):
                        safe_execute(
                            "delete_content_file",
                            os.remove,
                            doc.content_file_path,
                            error_collector=error_collector
                        )
                    
                    if doc.source_file_path and os.path.exists(doc.source_file_path):
                        safe_execute(
                            "delete_source_file",
                            os.remove,
                            doc.source_file_path,
                            error_collector=error_collector
                        )

                db.query(Question).filter(Question.session_id == session_id).delete()
                db.query(Flashcard).filter(Flashcard.session_id == session_id).delete()
                db.query(Document).filter(Document.session_id == session_id).delete()
                db.delete(session)
                db.commit()
                
                op.add_metadata(
                    documents_deleted=len(documents),
                    cleanup_errors=error_collector.get_summary() if error_collector.has_errors() else None
                )
                
            except Exception as e:
                traceback.print_exc()
                db.rollback()
                raise HTTPException(status_code=500, detail=str(e))

    @handle_database_errors
    def get_document(self, db: Session, document_id: str) -> Optional[Document]:
        with MonitoredOperation("get_document") as op:
            op.add_metadata(document_id=document_id)
            return db.query(Document).filter(Document.id == document_id).first()

    @handle_database_errors
    def get_documents(self, db: Session):
        with MonitoredOperation("get_documents"):
            documents = db.query(Document).all()
            monitoring_service.record_generation("get_documents", success=True, document_count=len(documents))
            return documents

    @handle_database_errors
    def get_documents_by_session(self, db: Session, session_id: str):
        with MonitoredOperation("get_documents_by_session") as op:
            op.add_metadata(session_id=session_id)
            documents = db.query(Document).filter(Document.session_id == session_id).all()
            op.add_metadata(documents_found=len(documents))
            return documents

    # @handle_database_errors
    # @validate_input(validate_document_request)
    def parse_document(self, db: Session, request: FileParseRequest, create_embeddings: bool = True) -> Document:
        with MonitoredOperation("parse_document") as op:
            op.add_metadata(
                filename=request.file.filename,
                file_size=request.file.size,
                content_type=request.file.content_type,
                create_embeddings=create_embeddings
            )
            
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
                    processing_status="processing" if create_embeddings else "completed",
                    text_length=len(raw_text),
                    session_id=request.session_id
                )
                
                db.add(document)
                db.commit()
                db.refresh(document)

                op.add_metadata(
                    document_id=document_id,
                    text_length=len(raw_text),
                    processing_status=document.processing_status
                )

                if create_embeddings:
                    try:
                        chunks = self.vector_processor.chunk_and_embed_document(db, document_id, raw_text)
                        document.processing_status = "completed"
                        db.commit()
                        
                        op.add_metadata(
                            chunks_created=len(chunks),
                            embedding_success=True
                        )
                        
                        logger.info(f"Created {len(chunks)} chunks with embeddings for document {document_id}")
                        
                    except Exception as e:
                        logger.warning(f"Embedding failed for {document_id}: {e}")
                        self._delete_document(db, document)
                        op.add_metadata(embedding_success=False, embedding_error=str(e))
                        raise HTTPException(status_code=500, detail="Embedding failed, document removed")

                return document

            except Exception as e:
                traceback.print_exc()
                db.rollback()
                
                # Cleanup temporary file
                if temp_file_path and os.path.exists(temp_file_path):
                    safe_execute("cleanup_temp_file", os.remove, temp_file_path)
                
                op.add_metadata(processing_success=False, error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
                
            finally:
                # Always cleanup temporary file
                if temp_file_path and os.path.exists(temp_file_path):
                    safe_execute("cleanup_temp_file", os.remove, temp_file_path)
    
    @handle_database_errors
    @validate_input(validate_document_request)
    def parse_audio_video(self, db: Session, request: FileParseRequest, create_embeddings: bool = True) -> Document:
        with MonitoredOperation("parse_audio_video") as op:
            op.add_metadata(
                filename=request.file.filename,
                file_size=request.file.size,
                content_type=request.file.content_type,
                create_embeddings=create_embeddings
            )
            
            allowed_types = {
                'audio/mpeg': 'audio', 'audio/wav': 'audio', 'audio/mp3': 'audio',
                'video/mp4': 'video', 'video/avi': 'video', 'video/quicktime': 'video',
                'video/x-msvideo': 'video'
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
                    processing_status="processing" if create_embeddings else "completed",
                    text_length=len(raw_text),
                    session_id=request.session_id
                )

                db.add(document)
                db.commit()
                db.refresh(document)

                op.add_metadata(
                    document_id=document_id,
                    text_length=len(raw_text),
                    processing_status=document.processing_status,
                    transcription_length=len(raw_text)
                )

                # Create embeddings if requested
                if create_embeddings:
                    try:
                        chunks = self.vector_processor.chunk_and_embed_document(db, document_id, raw_text)
                        document.processing_status = "completed"
                        db.commit()
                        
                        op.add_metadata(
                            chunks_created=len(chunks),
                            embedding_success=True
                        )
                        
                        logger.info(f"Created {len(chunks)} chunks with embeddings for audio/video document {document_id}")
                        
                    except Exception as e:
                        logger.warning(f"Embedding failed for {document_id}: {e}")
                        self._delete_document(db, document)
                        op.add_metadata(embedding_success=False, embedding_error=str(e))
                        raise HTTPException(status_code=500, detail="Embedding failed, document removed")

                return document

            except Exception as e:
                traceback.print_exc()
                db.rollback()
                
                if temp_file_path and os.path.exists(temp_file_path):
                    safe_execute("cleanup_temp_file", os.remove, temp_file_path)
                
                op.add_metadata(processing_success=False, error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
                
            finally:
                if temp_file_path and os.path.exists(temp_file_path):
                    safe_execute("cleanup_temp_file", os.remove, temp_file_path)
    
    @handle_database_errors
    def parse_web_url(self, db: Session, request: UrlParseRequest, create_embeddings: bool = True) -> Document:
        """ web URL parsing with comprehensive monitoring"""
        with MonitoredOperation("parse_web_url") as op:
            op.add_metadata(
                url=request.url,
                create_embeddings=create_embeddings
            )
            
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
                    source_file_path=None,
                    processing_status="processing" if create_embeddings else "completed",
                    text_length=len(raw_text),
                    session_id=request.session_id
                )

                db.add(document)
                db.commit()
                db.refresh(document)

                op.add_metadata(
                    document_id=document_id,
                    text_length=len(raw_text),
                    processing_status=document.processing_status,
                    url_length=len(request.url)
                )

                if create_embeddings:
                    try:
                        chunks = self.vector_processor.chunk_and_embed_document(db, document_id, raw_text)
                        document.processing_status = "completed"
                        db.commit()
                        
                        op.add_metadata(
                            chunks_created=len(chunks),
                            embedding_success=True
                        )
                        
                        logger.info(f"Created {len(chunks)} chunks with embeddings for web document {document_id}")
                        
                    except Exception as e:
                        logger.warning(f"Embedding failed for {document_id}: {e}")
                        self._delete_document(db, document)
                        op.add_metadata(embedding_success=False, embedding_error=str(e))
                        raise HTTPException(status_code=500, detail="Embedding failed, document removed")

                return document

            except Exception as e:
                traceback.print_exc()
                db.rollback()
                op.add_metadata(processing_success=False, error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
    
    @handle_database_errors
    def parse_youtube(self, db: Session, request: UrlParseRequest, create_embeddings: bool = True) -> Document:
        """ YouTube parsing with comprehensive monitoring"""
        with MonitoredOperation("parse_youtube") as op:
            op.add_metadata(
                url=request.url,
                create_embeddings=create_embeddings
            )
            
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
                    processing_status="processing" if create_embeddings else "completed",
                    text_length=len(raw_text),
                    session_id=request.session_id
                )

                db.add(document)
                db.commit()
                db.refresh(document)

                op.add_metadata(
                    document_id=document_id,
                    text_length=len(raw_text),
                    processing_status=document.processing_status,
                    transcription_length=len(raw_text)
                )

                if create_embeddings:
                    try:
                        chunks = self.vector_processor.chunk_and_embed_document(db, document_id, raw_text)
                        document.processing_status = "completed"
                        db.commit()
                        
                        op.add_metadata(
                            chunks_created=len(chunks),
                            embedding_success=True
                        )
                        
                        logger.info(f"Created {len(chunks)} chunks with embeddings for YouTube document {document_id}")
                        
                    except Exception as e:
                        logger.warning(f"Embedding failed for {document_id}: {e}")
                        self._delete_document(db, document)
                        op.add_metadata(embedding_success=False, embedding_error=str(e))
                        raise HTTPException(status_code=500, detail="Embedding failed, document removed")

                return document
    
            except Exception as e:
                traceback.print_exc()
                db.rollback()
                
                if audio_path and os.path.exists(audio_path):
                    safe_execute("cleanup_audio_file", self._cleanup_audio_directory, audio_path)
                
                op.add_metadata(processing_success=False, error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
                
            finally:
                if audio_path and os.path.exists(audio_path):
                    safe_execute("cleanup_audio_file", self._cleanup_audio_directory, audio_path)
    
    def _delete_document(self, db: Session, document: Document):
        try:
            if document.source_file_path and os.path.exists(document.source_file_path):
                safe_execute("cleanup_source_file", os.remove, document.source_file_path)
            if document.content_file_path and os.path.exists(document.content_file_path):
                safe_execute("cleanup_content_file", os.remove, document.content_file_path)
            
            db.delete(document)
            db.commit()
            logger.info(f"Deleted failed document {document.id}")
        except Exception as e:
            logger.error(f"Error cleaning up document {document.id}: {e}")
            db.rollback()

    def _cleanup_audio_directory(self, audio_path: str):
        """Cleanup audio file and its directory"""
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
            
            audio_dir = os.path.dirname(audio_path)
            if os.path.exists(audio_dir) and not os.listdir(audio_dir):
                os.rmdir(audio_dir)
                
        except Exception as e:
            logger.warning(f"Failed to cleanup audio directory: {e}")

document_service = DocumentService()