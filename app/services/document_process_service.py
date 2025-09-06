import uuid
import logging
import httpx
import re
import asyncio
import os
from typing import Optional, Dict
from sqlalchemy.orm import Session
from fastapi import HTTPException, UploadFile
from app.models import Document
from app.schemas.message import MessageResponse
from app.processors.content_processor import content_processor
from app.processors.vector_processor import vector_processor
from app.config import settings
from app.storages import get_storage_provider
from app.services.session_service import session_service
from bs4 import BeautifulSoup
import yt_dlp

logger = logging.getLogger(__name__)

FILE_TYPES = {
    'application/pdf': 'document', 
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'document',
    'image/jpeg': 'image', 'image/png': 'image', 'image/gif': 'image', 
    'image/bmp': 'image', 'image/tiff': 'image',
    'audio/mpeg': 'audio', 'audio/wav': 'audio', 'audio/mp3': 'audio',
    'video/mp4': 'video', 'video/avi': 'video', 'video/quicktime': 'video'
}

class DocumentProcessService:
    def __init__(self):
        self.content_processor = content_processor
        self.vector_processor = vector_processor
        self.storage = get_storage_provider()

    def _get_file_category(self, content_type: str) -> Optional[str]:
        return FILE_TYPES.get(content_type)

    def _detect_source_type(self, source) -> str:
        if isinstance(source, str):
            if 'youtube.com' in source or 'youtu.be' in source:
                return 'youtube'
            return 'web'
        else:  
            content_type = getattr(source, 'content_type', '')
            return self._get_file_category(content_type) or 'document'

    async def process_file(self, db: Session, file: UploadFile, session_id: Optional[str] = None) -> Document:
        if not self._get_file_category(file.content_type):
            raise HTTPException(
                status_code=400, 
                detail=MessageResponse.create(
                    translation_key="unsupportedFileType",
                    message="Unsupported file type"
                ).model_dump()
            )
        
        document_id = str(uuid.uuid4())
        source_type = self._detect_source_type(file)
        
        return await self._process_document(
            db=db,
            document_id=document_id,
            source_type=source_type,
            source_data=file,
            session_id=session_id,
            metadata=self._extract_file_metadata(file)
        )

    async def process_url(self, db: Session, url: str, session_id: Optional[str] = None) -> Document:
        document_id = str(uuid.uuid4())
        source_type = self._detect_source_type(url)
        
        if source_type == 'youtube':
            metadata = await self._extract_youtube_metadata(url)
        else:
            metadata = await self._extract_web_metadata(url)
        
        return await self._process_document(
            db=db,
            document_id=document_id,
            source_type=source_type,
            source_data=url,
            session_id=session_id,
            metadata=metadata
        )

    def _extract_file_metadata(self, file: UploadFile) -> Dict:
        return {
            'filename': file.filename or 'unknown',
            'content_type': file.content_type or '',
            'size': getattr(file, 'size', 0)
        }

    async def _extract_youtube_metadata(self, url: str) -> Dict:
        try:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noplaylist": True,
                "ignore_no_formats_error": True,
                "ignoreerrors": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False, process=False)

            title = re.sub(r'[<>:"/\\|?*]', '_', info.get("title", "video"))
            return {
                "title": title,
                "url": url,
                "duration": info.get("duration") or 0,
            }
        except Exception as e:
            logger.error(f"YouTube metadata extraction failed: {e}")
            return {"title": url, "url": url, "error": str(e)}

    async def _extract_web_metadata(self, url: str) -> Dict:
        try:
            async with httpx.AsyncClient(timeout=settings.content.request_timeout) as client:
                response = await client.get(url, headers={'User-Agent': settings.content.user_agent})
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                title = (soup.find('title') or soup.find('meta', {'property': 'og:title'}))
                title = title.get_text().strip() if title else url.split('/')[-1]
                
                return {'title': title, 'url': url}
        except Exception as e:
            logger.error(f"Web metadata extraction failed: {e}")
            return {'title': url.split('/')[-1], 'url': url, 'error': str(e)}

    async def _process_document(self, db: Session, document_id: str, source_type: str, 
                              source_data, session_id: Optional[str], metadata: Dict) -> Document:
        try:
            if source_type == 'document':
                source_file_path = self.storage.save_source_file(source_data, document_id)
                raw_text = await self.content_processor.process_pdf_docx(source_file_path)
                file_type = 'pdf' if 'pdf' in getattr(source_data, 'content_type', '') else 'docx'
            elif source_type == 'image':
                source_file_path = self.storage.save_source_file(source_data, document_id)
                raw_text = await self.content_processor.process_image(source_file_path)
                file_type = 'image'
            elif source_type in ['audio', 'video']:
                source_file_path = self.storage.save_source_file(source_data, document_id)
                raw_text = await self.content_processor.process_audio_video(source_file_path)
                file_type = source_type
            elif source_type == 'web':
                raw_text = await self.content_processor.process_web_url(source_data)
                source_file_path = source_data
                file_type = 'web'
            elif source_type == 'youtube':
                raw_text = await self.content_processor.process_youtube_url(source_data)
                source_file_path = source_data
                file_type = 'youtube'
            else:
                raise HTTPException(
                    status_code=400, 
                    detail=MessageResponse.create(
                        translation_key="unsupportedSourceType",
                        message="Unsupported source type"
                    ).model_dump()
                )

            content_file_path = self.storage.save_content_file(raw_text, document_id)
            storage_response = self.storage.get_storage_response(content_file_path, source_file_path)

            filename = getattr(source_data, 'filename', source_data)
            source_name = None

            if 'UploadFile' in type(source_data).__name__ or hasattr(source_data, 'filename') and hasattr(source_data, 'content_type'):
                source_name = self.storage.get_file_name_without_extension(source_data.filename)

            doc_data = {
                "id": document_id,
                "filename": getattr(source_data, 'filename', source_data),
                "source_name": metadata.get(
                    "title",
                    source_name if source_name else filename
                ),
                "file_type": file_type,
                "source_type": "youtube" if source_type == "youtube"
                            else "url" if source_type == "web"
                            else "upload",
                "content_file_path": storage_response.content_file_path,
                "source_file_path": storage_response.source_file_path,
                "file_size": getattr(source_data, 'size', None),
                "processing_status": "processing",
                "text_length": len(raw_text),
                "extra_metadata": metadata,
                "session_id": session_id,
                "storage_provider": storage_response.provider,
                "storage_bucket": None,
            }

            document = Document(**doc_data)
            db.add(document)
            db.commit()
            db.refresh(document)

            await self._process_embeddings(db, document, raw_text, session_id)
            
            return document

        except Exception as e:
            db.rollback()
            logger.error(f"Document processing failed: {e}")
            raise HTTPException(
                status_code=500, 
                detail=MessageResponse.create(
                    translation_key="documentProcessingFailed",
                    message="Document processing failed"
                ).model_dump()
            )

    async def _process_embeddings(self, db: Session, document: Document, raw_text: str, session_id: Optional[str]):
        try:
            chunks = self.vector_processor.chunk_and_embed_document(db, document.id, raw_text)
            document.processing_status = "completed"
            db.commit()
            if session_id:
                session_service.update_session_documents(db, session_id, True)
            logger.info(f"Created {len(chunks)} chunks for document {document.id}")
        except Exception as e:
            logger.error(f"Embedding failed for {document.id}: {e}")
            self._cleanup_document(db, document)
            if session_id:
                session_service.update_session_documents(db, session_id, False)
            raise HTTPException(
                status_code=500, 
                detail=MessageResponse.create(
                    translation_key="embeddingFailed",
                    message="Embedding failed"
                ).model_dump()
            )

    def _cleanup_document(self, db: Session, document: Document):
        try:
            storage = get_storage_provider(document.storage_provider or "local")
            for file_path in filter(None, [document.source_file_path, document.content_file_path]):
                try:
                    storage.delete_file(file_path)
                except Exception as e:
                    logger.warning(f"File cleanup failed for {file_path}: {e}")
            
            db.delete(document)
            db.commit()
            logger.info(f"Deleted document {document.id}")
        except Exception as e:
            logger.error(f"Error deleting document {document.id}: {e}")
            db.rollback()

document_process_service = DocumentProcessService()
