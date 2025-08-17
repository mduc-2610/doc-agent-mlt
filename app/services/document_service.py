import uuid
import os
import traceback
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, UploadFile
from app.models import Document, Session as SessionModel
from app.processors.content_processor import content_processor
from app.processors.vector_processor import vector_processor
from app.config import settings, current_date_time

class DocumentService:
    def __init__(self):
        self.content_processor = content_processor
        self.vector_processor = vector_processor

    def get_sessions(self, db: Session):
        return db.query(SessionModel).all()

    def create_session(self, db: Session, user_id: str, name: str, description: str = "") -> SessionModel:
        try:
            session = SessionModel(user_id=user_id, name=name, description=description)
            db.add(session)
            db.commit()
            db.refresh(session)
            return session
        except Exception as e:
            traceback.print_exc()
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    def get_session(self, db: Session, session_id: str) -> Optional[SessionModel]:
        return db.query(SessionModel).filter(SessionModel.id == session_id).first()

    def get_user_sessions(self, db: Session, user_id: str):
        return db.query(SessionModel).filter(SessionModel.user_id == user_id).all()

    def update_session(self, db: Session, session_id: str, name: str = None, description: str = None):
        try:
            session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
            if name is not None:
                session.name = name
            if description is not None:
                session.description = description
            session.updated_at = current_date_time()
            db.commit()
            return session
        except Exception as e:
            traceback.print_exc()
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    def delete_session(self, db: Session, session_id: str):
        try:
            session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            documents = db.query(Document).filter(Document.session_id == session_id).all()
            for doc in documents:
                if doc.content_file_path and os.path.exists(doc.content_file_path):
                    try:
                        os.remove(doc.content_file_path)
                    except:
                        pass

            db.query(Document).filter(Document.session_id == session_id).delete()
            db.delete(session)
            db.commit()
        except Exception as e:
            traceback.print_exc()
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    def get_document(self, db: Session, document_id: str) -> Optional[Document]:
        return db.query(Document).filter(Document.id == document_id).first()

    def get_documents(self, db: Session):
        return db.query(Document).all()

    def get_documents_by_session(self, db: Session, session_id: str):
        return db.query(Document).filter(Document.session_id == session_id).all()

    def parse_document(self, db: Session, file: UploadFile, session_id: str = None, create_embeddings: bool = True) -> Document:
        allowed_types = {
            'application/pdf': 'pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
            'image/jpeg': 'image', 'image/png': 'image', 'image/gif': 'image',
            'image/bmp': 'image', 'image/tiff': 'image'
        }
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        file_type = allowed_types[file.content_type]
        document_id = str(uuid.uuid4())
        temp_file_path = None

        try:
            temp_file_path = self.content_processor.save_temp_file(file)
            
            if file_type in ['pdf', 'docx']:
                raw_text = self.content_processor.process_pdf_docx(temp_file_path)
            elif file_type == 'image':
                raw_text = self.content_processor.process_image(temp_file_path)
            else:
                raise HTTPException(status_code=400, detail="Unsupported file type")

            content_file_path = self.content_processor.save_content_to_file(raw_text, document_id)
            document = Document(
                id=document_id,
                filename=file.filename,
                file_type=file_type,
                source_type="upload",
                content_file_path=content_file_path,
                file_size=file.size,
                processing_status="processing" if create_embeddings else "completed",
                text_length=len(raw_text),
                session_id=session_id
            )

            db.add(document)
            db.commit()
            db.refresh(document)

            if create_embeddings:
                try:
                    chunks = self.vector_processor.chunk_and_embed_document(db, document_id, raw_text)
                    document.processing_status = "completed"
                    db.commit()
                    print(f"Created {len(chunks)} chunks with embeddings for document {document_id}")
                except Exception as e:
                    print(f"Warning: Failed to create embeddings: {e}")
                    document.processing_status = "completed_no_embeddings"
                    db.commit()

            return document

        except Exception as e:
            traceback.print_exc()
            db.rollback()
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    def parse_audio_video(self, db: Session, file: UploadFile, session_id: str = None, create_embeddings: bool = True) -> Document:
        allowed_types = {
            'audio/mpeg': 'audio', 'audio/wav': 'audio', 'audio/mp3': 'audio',
            'video/mp4': 'video', 'video/avi': 'video', 'video/quicktime': 'video',
            'video/x-msvideo': 'video'
        }
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Unsupported audio/video file type")

        file_type = allowed_types[file.content_type]
        document_id = str(uuid.uuid4())
        temp_file_path = None

        try:
            temp_file_path = self.content_processor.save_temp_file(file)
            raw_text = self.content_processor.process_audio_video(temp_file_path)
            content_file_path = self.content_processor.save_content_to_file(raw_text, document_id)

            document = Document(
                id=document_id,
                filename=file.filename,
                file_type=file_type,
                source_type="upload",
                content_file_path=content_file_path,
                file_size=file.size,
                processing_status="processing" if create_embeddings else "completed",
                text_length=len(raw_text),
                session_id=session_id
            )

            db.add(document)
            db.commit()
            db.refresh(document)

            if create_embeddings:
                try:
                    chunks = self.vector_processor.chunk_and_embed_document(db, document_id, raw_text)
                    document.processing_status = "completed"
                    db.commit()
                    print(f"Created {len(chunks)} chunks with embeddings for document {document_id}")
                except Exception as e:
                    print(f"Warning: Failed to create embeddings: {e}")
                    document.processing_status = "completed_no_embeddings"
                    db.commit()

            return document

        except Exception as e:
            traceback.print_exc()
            db.rollback()
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    def parse_web_url(self, db: Session, url: str, session_id: str = None, create_embeddings: bool = True) -> Document:
        document_id = str(uuid.uuid4())

        try:
            raw_text = self.content_processor.process_web_url(url)
            content_file_path = self.content_processor.save_content_to_file(raw_text, document_id)

            document = Document(
                id=document_id,
                filename=url,
                file_type="web",
                source_type="url",
                content_file_path=content_file_path,
                processing_status="processing" if create_embeddings else "completed",
                text_length=len(raw_text),
                session_id=session_id
            )

            db.add(document)
            db.commit()
            db.refresh(document)

            if create_embeddings:
                try:
                    chunks = self.vector_processor.chunk_and_embed_document(db, document_id, raw_text)
                    document.processing_status = "completed"
                    db.commit()
                    print(f"Created {len(chunks)} chunks with embeddings for document {document_id}")
                except Exception as e:
                    print(f"Warning: Failed to create embeddings: {e}")
                    document.processing_status = "completed_no_embeddings"
                    db.commit()

            return document

        except Exception as e:
            traceback.print_exc()
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    def parse_youtube(self, db: Session, url: str, session_id: str = None, create_embeddings: bool = True) -> Document:
        document_id = str(uuid.uuid4())
        audio_path = None

        try:
            audio_path = self.content_processor.download_youtube_video(url)
            raw_text = self.content_processor.process_audio_video(audio_path)
            content_file_path = self.content_processor.save_content_to_file(raw_text, document_id)

            document = Document(
                id=document_id,
                filename=url,
                file_type="youtube",
                source_type="youtube",
                content_file_path=content_file_path,
                processing_status="processing" if create_embeddings else "completed",
                text_length=len(raw_text),
                session_id=session_id
            )

            db.add(document)
            db.commit()
            db.refresh(document)

            if create_embeddings:
                try:
                    chunks = self.vector_processor.chunk_and_embed_document(db, document_id, raw_text)
                    document.processing_status = "completed"
                    db.commit()
                    print(f"Created {len(chunks)} chunks with embeddings for document {document_id}")
                except Exception as e:
                    print(f"Warning: Failed to create embeddings: {e}")
                    document.processing_status = "completed_no_embeddings"
                    db.commit()

            return document

        except Exception as e:
            traceback.print_exc()
            db.rollback()
            if audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                    os.rmdir(os.path.dirname(audio_path))
                except:
                    pass
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            if audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                    os.rmdir(os.path.dirname(audio_path))
                except:
                    pass

document_service = DocumentService()