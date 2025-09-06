from typing import Dict, Type
from .base import StorageProvider
from .local_provider import LocalStorageProvider
from .minio_provider import MinIOStorageProvider
from app.config import settings

class StorageFactory:
    """Factory for creating storage providers"""
    
    _providers: Dict[str, Type[StorageProvider]] = {
        "local": LocalStorageProvider,
        "minio": MinIOStorageProvider,
    }
    
    @classmethod
    def register_provider(cls, name: str, provider_class: Type[StorageProvider]):
        """Register a new storage provider"""
        cls._providers[name] = provider_class
    
    @classmethod
    def create_provider(cls, provider_name: str) -> StorageProvider:
        """Create a storage provider instance"""
        if provider_name not in cls._providers:
            raise ValueError(f"Unknown storage provider: {provider_name}")
        
        provider_class = cls._providers[provider_name]
        return provider_class()
    
    @classmethod
    def get_available_providers(cls) -> list[str]:
        """Get list of available provider names"""
        return list(cls._providers.keys())

_storage_provider = None
def get_storage_provider(provider_name: str = None) -> StorageProvider:
    global _storage_provider
    if _storage_provider: return _storage_provider
    
    _storage_provider = StorageFactory.create_provider(provider_name=provider_name or settings.storage.storage_provider)
    return _storage_provider
