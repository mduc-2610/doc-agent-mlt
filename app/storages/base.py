from abc import ABC, abstractmethod
from typing import Optional, BinaryIO
from pydantic import BaseModel
from fastapi import UploadFile
import os
import urllib.parse


class StorageResponse(BaseModel):
    provider: str
    content_file_path: str
    source_file_path: Optional[str] = None

class StorageProvider(ABC):
    
    def __init__(self, provider_name: str):
        self.provider_name = provider_name
    
    # ===== ABSTRACT METHODS =====
    
    @abstractmethod
    def _write_bytes(self, directory: str, filename: str, content: bytes) -> str:
        pass
    
    @abstractmethod
    def _write_stream(self, directory: str, filename: str, fileobj: BinaryIO) -> str:
        pass
    
    @abstractmethod
    def _read_bytes(self, file_path: str) -> bytes:
        pass
    
    @abstractmethod
    def _delete(self, file_path: str) -> bool:
        pass
    
    @abstractmethod
    def _exists(self, file_path: str) -> bool:
        pass
    
    # ===== CORE OPERATIONS =====
    
    def save_content_file(self, content: str, document_id: str) -> str:
        content_bytes = content.encode('utf-8')
        return self._write_bytes("content", f"{document_id}.txt", content_bytes)
    
    def save_summary_file(self, content: str, document_id: str) -> str:
        content_bytes = content.encode('utf-8')
        return self._write_bytes("summary", f"{document_id}_summary.txt", content_bytes)
    
    def save_source_file(self, file: UploadFile, document_id: str) -> str:
        ext = self._get_file_extension(file)
        filename = f"{document_id}{ext}"
        try:
            file.file.seek(0)
        except Exception:
            pass
        return self._write_stream("source", filename, file.file)
    
    def create_temp_file(self, extension: str = ".tmp") -> str:
        """Create a temporary file in the tmp storage location and return its path"""
        import uuid
        filename = f"temp_{uuid.uuid4().hex}{extension}"
        content = b""  # Create empty file
        return self._write_bytes("tmp", filename, content)
    
    def save_temp_file(self, temp_local_path: str, document_id: str) -> str:
        """Save a temporary file to the tmp storage location"""
        filename = f"{document_id}{os.path.splitext(temp_local_path)[1]}"
        with open(temp_local_path, 'rb') as f:
            content = f.read()
        return self._write_bytes("tmp", filename, content)
    
    def cleanup_temp_file(self, file_path: str) -> bool:
        """Clean up temporary file using storage provider's delete method"""
        return self._delete(file_path)
    
    def read_file(self, file_path: str) -> str:
        content_bytes = self._read_bytes(file_path)
        return content_bytes.decode('utf-8')
    
    def delete_file(self, file_path: str) -> bool:
        return self._delete(file_path)
    
    def file_exists(self, file_path: str) -> bool:
        return self._exists(file_path)
    
    def get_storage_response(self, content_file_path: str, source_file_path: Optional[str] = None) -> StorageResponse:
        return StorageResponse(
            provider=self.provider_name,
            content_file_path=content_file_path,
            source_file_path=source_file_path
        )

    def get_file_name_without_extension(self, file_path: str) -> str:
        parsed_url = urllib.parse.urlparse(file_path)
        return (os.path.basename(parsed_url.path).rsplit('.', 1)[0]).split('?')[0]
    
    def _get_file_extension(self, file: UploadFile) -> str:
        if file.filename:
            _, ext = os.path.splitext(file.filename)
            return ext or ".bin"
        return ".bin"
    
    def get_file_extension_from_url(self, url: str) -> str:
        parsed_url = urllib.parse.urlparse(url)
        path = parsed_url.path
        if '.' in path:
            ext = os.path.splitext(path)[1].lower()
            if ext in ['.pdf', '.docx', '.doc']:
                return ext
        return '.pdf'  
