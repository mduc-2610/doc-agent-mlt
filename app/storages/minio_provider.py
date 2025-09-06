import os
import io
from typing import Optional, BinaryIO
from fastapi import UploadFile
from minio import Minio
from minio.error import S3Error
from .base import StorageProvider
from app.config import settings

class MinIOStorageProvider(StorageProvider):
    
    def __init__(self):
        super().__init__("minio")
        
        self.dir_mapping = {
            "content": "dc-ag-content-files",
            "source": "dc-ag-source-files",
            "tmp": "dc-ag-tmp-files", 
            "summary": "dc-ag-summary-files"
        }
        
        self.client = Minio(
            endpoint=settings.minio.endpoint,
            access_key=settings.minio.access_key,
            secret_key=settings.minio.secret_key,
            secure=settings.minio.secure,
            region=getattr(settings.minio, 'region', 'us-east-1')
        )
        
        protocol = "https" if settings.minio.secure else "http"
        self.base_url = f"{protocol}://{settings.minio.endpoint}"
        self._ensure_buckets()
    
    def _ensure_buckets(self):
        for bucket_name in self.dir_mapping.values():
            try:
                if not self.client.bucket_exists(bucket_name):
                    self.client.make_bucket(bucket_name)
            except S3Error as e:
                print(f"Warning: Could not create/check bucket {bucket_name}: {e}")
    
    def _get_file_url(self, bucket_name: str, object_name: str) -> str:
        return f"{self.base_url}/{bucket_name}/{object_name}"
    
    def _parse_url(self, file_url: str) -> tuple[str, str]:
        if file_url.startswith(self.base_url):
            path_part = file_url[len(self.base_url):].lstrip('/')
            parts = path_part.split('/', 1)
            if len(parts) == 2:
                return parts[0], parts[1]
        raise ValueError(f"Invalid file URL format: {file_url}")
    
    def _write_bytes(self, directory: str, filename: str, content: bytes) -> str:
        bucket_name = self.dir_mapping.get(directory, f"dc-ag-{directory}-files")
        
        try:
            self.client.put_object(
                bucket_name=bucket_name,
                object_name=filename,
                data=io.BytesIO(content),
                length=len(content),
                content_type="application/octet-stream"
            )
            return self._get_file_url(bucket_name, filename)
        except S3Error as e:
            raise Exception(f"Failed to write file: {e}")
    
    def _write_stream(self, directory: str, filename: str, fileobj: BinaryIO) -> str:
        bucket_name = self.dir_mapping.get(directory, f"dc-ag-{directory}-files")
        
        try:
            fileobj.seek(0)
        except Exception:
            pass
                
        try:
            self.client.put_object(
                bucket_name=bucket_name,
                object_name=filename,
                data=fileobj,
                length=-1,
                part_size=10 * 1024 * 1024,
                content_type="application/octet-stream"
            )
            return self._get_file_url(bucket_name, filename)
        except S3Error as e:
            raise Exception(f"Failed to write stream: {e}")
    
    def _read_bytes(self, file_path: str) -> bytes:
        bucket_name, object_name = self._parse_url(file_path)
        try:
            response = self.client.get_object(bucket_name, object_name)
            return response.read()
        except S3Error as e:
            raise Exception(f"Failed to read file: {e}")
        finally:
            if 'response' in locals():
                response.close()
                response.release_conn()
    
    def _delete(self, file_path: str) -> bool:
        try:
            bucket_name, object_name = self._parse_url(file_path)
            self.client.remove_object(bucket_name, object_name)
            return True
        except S3Error:
            return False
    
    def _exists(self, file_path: str) -> bool:
        try:
            bucket_name, object_name = self._parse_url(file_path)
            self.client.stat_object(bucket_name, object_name)
            return True
        except S3Error:
            return False
    

