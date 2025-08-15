import uuid
import os
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, UploadFile
from app.models import Document, Session as SessionModel
from app.services.processor import (
    process_pdf_docx, process_image, process_web_url, 
    download_youtube_video, process_audio_video, save_temp_file, save_content_to_file
)
from app.config import settings, current_date_time
import traceback

def create_session(db: Session, user_id: str, name: str, description: str = "") -> SessionModel:
    try:
        session = SessionModel(
            user_id=user_id,
            name=name,
            description=description
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session
    except Exception as e:
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

def get_session(db: Session, session_id: str) -> Optional[SessionModel]:
    return db.query(SessionModel).filter(SessionModel.id == session_id).first()

def get_user_sessions(db: Session, user_id: str):
    return db.query(SessionModel).filter(SessionModel.user_id == user_id).all()

def update_session(db: Session, session_id: str, name: str = None, description: str = None):
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

def delete_session(db: Session, session_id: str):
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

def parse_document(db: Session, file: UploadFile, session_id: str = None) -> Document:
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
        temp_file_path = save_temp_file(file)
        
        if file_type in ['pdf', 'docx']:
            raw_text = process_pdf_docx(temp_file_path)
        elif file_type == 'image':
            raw_text = process_image(temp_file_path)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")
        
        content_file_path = save_content_to_file(raw_text, document_id)
        
        document = Document(
            id=document_id,
            filename=file.filename,
            file_type=file_type,
            source_type="upload",
            content_file_path=content_file_path,
            file_size=file.size,
            processing_status="completed",
            text_length=len(raw_text),
            session_id=session_id
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
        
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

def parse_audio_video(db: Session, file: UploadFile, session_id: str = None) -> Document:
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
        temp_file_path = save_temp_file(file)
        raw_text = process_audio_video(temp_file_path)
        content_file_path = save_content_to_file(raw_text, document_id)
        
        document = Document(
            id=document_id,
            filename=file.filename,
            file_type=file_type,
            source_type="upload",
            content_file_path=content_file_path,
            file_size=file.size,
            processing_status="completed",
            text_length=len(raw_text),
            session_id=session_id
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
                
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

def parse_web_url(db: Session, url: str, session_id: str = None) -> Document:
    document_id = str(uuid.uuid4())
    
    try:
        raw_text = process_web_url(url)
        content_file_path = save_content_to_file(raw_text, document_id)
        
        document = Document(
            id=document_id,
            filename=url,
            file_type="web",
            source_type="url",
            content_file_path=content_file_path,
            processing_status="completed",
            text_length=len(raw_text),
            session_id=session_id
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
                
        return document
        
    except Exception as e:
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

def parse_youtube(db: Session, url: str, session_id: str = None) -> Document:
    document_id = str(uuid.uuid4())
    audio_path = None
    
    try:
        audio_path = download_youtube_video(url)
        raw_text = process_audio_video(audio_path)
        content_file_path = save_content_to_file(raw_text, document_id)
        
        document = Document(
            id=document_id,
            filename=url,
            file_type="youtube",
            source_type="youtube",
            content_file_path=content_file_path,
            processing_status="completed",
            text_length=len(raw_text),
            session_id=session_id
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
        
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

def get_document(db: Session, document_id: str) -> Optional[Document]:
    return db.query(Document).filter(Document.id == document_id).first()

def get_documents(db: Session):
    return db.query(Document).all()

def get_documents_by_session(db: Session, session_id: str):
    return db.query(Document).filter(Document.session_id == session_id).all()   