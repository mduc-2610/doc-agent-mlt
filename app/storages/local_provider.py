import os
import shutil
from typing import Optional, BinaryIO
from fastapi import UploadFile
from .base import StorageProvider
from app.config import settings

class LocalStorageProvider(StorageProvider):
    
    def __init__(self):
        super().__init__("local")
        self.base_dir = "local_fs"
        self.base_url = getattr(settings, 'local_base_url', 'http://localhost:8000/local_fs')
        
        self.dir_mapping = {
            "content": "dc-ag-content-files",
            "source": "dc-ag-source-files", 
            "tmp": "dc-ag-tmp-files",
            "summary": "dc-ag-summary-files"
        }
        
        self._ensure_directories()
    
    def _ensure_directories(self):
        for directory in self.dir_mapping.values():
            path = os.path.join(self.base_dir, directory)
            os.makedirs(path, exist_ok=True)
    
    def _get_file_url(self, directory: str, filename: str) -> str:
        return f"{self.base_url}/{directory}/{filename}"
    
    def _url_to_file_path(self, file_url: str) -> str:
        if file_url.startswith(self.base_url):
            relative_path = file_url[len(self.base_url):].lstrip('/')
            return os.path.join(self.base_dir, relative_path)
        return file_url
    
    def _write_bytes(self, directory: str, filename: str, content: bytes) -> str:
        actual_directory = self.dir_mapping.get(directory, directory)
        
        file_path = os.path.join(self.base_dir, actual_directory, filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'wb') as f:
            f.write(content)
        return self._get_file_url(actual_directory, filename)
    
    def _write_stream(self, directory: str, filename: str, fileobj: BinaryIO) -> str:
        actual_directory = self.dir_mapping.get(directory, directory)
        
        file_path = os.path.join(self.base_dir, actual_directory, filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        try:
            fileobj.seek(0)
        except Exception:
            pass
            
        with open(file_path, "wb") as out_f:
            shutil.copyfileobj(fileobj, out_f, length=64 * 1024)
        return self._get_file_url(actual_directory, filename)
    
    def _read_bytes(self, file_path: str) -> bytes:
        local_path = self._url_to_file_path(file_path)
        with open(local_path, 'rb') as f:
            return f.read()
    
    def _delete(self, file_path: str) -> bool:
        try:
            local_path = self._url_to_file_path(file_path)
            if os.path.exists(local_path):
                os.remove(local_path)
                return True
            return False
        except Exception:
            return False
    
    def _exists(self, file_path: str) -> bool:
        local_path = self._url_to_file_path(file_path)
        return os.path.exists(local_path)
