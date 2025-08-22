# app/config.py -  configuration
import os
from datetime import datetime, timezone
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from typing import Optional, List

load_dotenv(override=True)

class RAGSettings(BaseSettings):
    embedding_model_name: str = "BAAI/bge-large-en-v1.5"
    embedding_dimension: int = 1024
    embedding_batch_size: int = 32
    
    retrieval_top_k: int = 10
    rerank_top_k: int = 5
    similarity_threshold: float = 0.5
    diversity_threshold: float = 0.7
    enable_hybrid_search: bool = True
    
    max_context_length: int = 4000
    chunk_overlap_ratio: float = 0.1
    adaptive_chunking: bool = True
    
    min_question_quality_score: float = 0.7
    context_relevance_threshold: float = 0.6
    enable_content_filtering: bool = True
    
    enable_embedding_cache: bool = True
    cache_ttl_seconds: int = 3600  # 1 hour
    max_cache_size: int = 10000
    enable_batch_processing: bool = True
    
    max_retries: int = 3
    retry_delay_base: float = 1.0 
    generation_timeout: int = 30
    
    class Config:
        case_sensitive = False

class DatabaseSettings(BaseSettings):
    database_url: str = os.getenv("DATABASE_URL")
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600
    echo: bool = False
    
    class Config:
        case_sensitive = False

class Settings(BaseSettings):
    llama_cloud_api_key: str = os.getenv("LLAMA_CLOUD_API_KEY")
    openai_api_key: str = os.getenv("OPENAI_API_KEY")
    hf_api_key: str = os.getenv("HF_API_KEY", "")
    
    temp_files_dir: str = "document_files/tmp_dir"
    content_files_dir: str = "document_files/content_files"
    source_files_dir: str = "document_files/source_files"
    summary_files_dir: str = "document_files/summary_files"
    cache_dir: str = "document_files/cache"

    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    max_file_size_mb: int = 100
    max_concurrent_processing: int = 4
    
    rag: RAGSettings = RAGSettings()
    database: DatabaseSettings = DatabaseSettings()
    
    class Config:
        case_sensitive = False

settings = Settings()

def current_date_time():
    return datetime.now(timezone.utc)