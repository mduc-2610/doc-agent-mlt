# app/config.py -  configuration
import os
from datetime import datetime, timezone
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from typing import Optional, List

load_dotenv(override=True)

class AudioProcessingSettings(BaseSettings):
    model_name: str = "openai/whisper-small"
    sample_rate: int = 16000
    chunk_duration: int = 30  
    min_chunk_duration: float = 0.5  
    max_tokens: int = 448
    num_beams: int = 5
    
    audio_codec: str = "pcm_s16le"
    audio_channels: int = 1
    
    class Config:
        case_sensitive = False

class ContentProcessingSettings(BaseSettings):
    max_file_size_mb: int = 100
    request_timeout: int = 100
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    max_context_chars: int = 6000
    context_truncation_suffix: str = "\n[Content truncated]"
    
    class Config:
        case_sensitive = False

class VectorProcessingSettings(BaseSettings):
    max_cache_size: int = 5000
    max_generation_cache_size: int = 1000
    
    min_context_chars: int = 100
    context_separator: str = "\n\n"
    
    class Config:
        case_sensitive = False

class QuestionGenerationSettings(BaseSettings):
    model_name: str = "deepseek/deepseek-r1-0528:free"
    base_url: str = "https://openrouter.ai/api/v1"
    http_referer: str = "https://openrouter.ai/deepseek/deepseek-r1-0528:free"
    x_title: str = "DeepSeek: R1 0528 (free)"
    headers: dict = {
        "HTTP-Referer": http_referer,
        "X-Title": x_title
    }
    
    max_questions_per_request: int = 30
    max_flashcards_per_request: int = 30
    questions_per_chunk: int = 15
    flashcards_per_chunk: int = 15
    
    class Config:
        case_sensitive = False

class ChunkSettings(BaseSettings):
    small_doc_threshold: int = 2000
    medium_doc_threshold: int = 8000
    large_doc_threshold: int = 20000
    
    small_doc_chunk_size: int = 800
    medium_doc_chunk_size: int = 1500
    large_doc_chunk_size: int = 2500
    xlarge_doc_chunk_size: int = 3500
    
    small_doc_chunk_overlap: int = 100
    medium_doc_chunk_overlap: int = 150
    large_doc_chunk_overlap: int = 200
    xlarge_doc_chunk_overlap: int = 300
    
    chars_per_token_estimate: int = 6
    text_separators: List[str] = ["\n\n", "\n", ". ", " ", ""]
    
    class Config:
        case_sensitive = False

class RAGSettings(BaseSettings):
    embedding_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dimension: int = 384
    embedding_batch_size: int = 128
    
    retrieval_top_k: int = 8
    similarity_threshold: float = 0.5
    
    max_context_length: int = 3000
    chunk_overlap_ratio: float = 0.1
    adaptive_chunking: bool = True
    
    min_question_quality_score: float = 0.6
    context_relevance_threshold: float = 0.5
    enable_content_filtering: bool = True
    
    enable_embedding_cache: bool = True
    cache_ttl_seconds: int = 3600
    max_cache_size: int = 10000
    enable_batch_processing: bool = True
    
    max_retries: int = 2
    retry_delay_base: float = 0.5
    generation_timeout: int = 20
    
    class Config:
        case_sensitive = False

class MinIOSettings(BaseSettings):
    endpoint: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    access_key: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key: str = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
    secure: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"
    region: str = os.getenv("MINIO_REGION", "us-east-1")
    
    class Config:
        case_sensitive = False

class StorageSettings(BaseSettings):
    storage_provider : str = os.getenv("STORAGE_PROVIDER", "local")
    local_path : str = "local_fs"

    class Config:
        case_sensitive = False

class DatabaseSettings(BaseSettings):
    database_url: str = os.getenv("DATABASE_URL")
    use_aws_db: bool = os.getenv("USE_AWS_DB", "false").lower() == "true"

    aws_db_host: Optional[str] = os.getenv("AWS_DB_HOST")
    aws_db_port: int = int(os.getenv("AWS_DB_PORT", "5432"))
    aws_db_name: str = os.getenv("AWS_DB_NAME", "document_processor")
    aws_db_user: str = os.getenv("AWS_DB_USER", "postgres")
    aws_db_password: str = os.getenv("AWS_DB_PASSWORD")
    aws_db_ssl_mode: str = os.getenv("AWS_DB_SSL_MODE", "require")
    
    local_db_host: str = os.getenv("LOCAL_DB_HOST", "localhost")
    local_db_port: int = int(os.getenv("LOCAL_DB_PORT", "5433"))
    local_db_name: str = os.getenv("LOCAL_DB_NAME", "document_processor")
    local_db_user: str = os.getenv("LOCAL_DB_USER", "postgres")
    local_db_password: str = os.getenv("LOCAL_DB_PASSWORD", "root")
    
    pool_size: int = int(os.getenv("DB_POOL_SIZE", "5"))
    max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    pool_timeout: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    pool_recycle: int = int(os.getenv("DB_POOL_RECYCLE", "3600"))
    echo: bool = os.getenv("DB_ECHO", "false").lower() == "true"
    
    
    def get_database_url(self) -> str:
        if self.use_aws_db and self.aws_db_host and self.aws_db_password:
            return (
                f"postgresql://{self.aws_db_user}:{self.aws_db_password}@"
                f"{self.aws_db_host}:{self.aws_db_port}/{self.aws_db_name}"
                f"?sslmode={self.aws_db_ssl_mode}"
            )
        else:
            return (
                f"postgresql://{self.local_db_user}:{self.local_db_password}@"
                f"{self.local_db_host}:{self.local_db_port}/{self.local_db_name}"
            )
    
    class Config:
        case_sensitive = False

class Settings(BaseSettings):
    llama_cloud_api_key: str = os.getenv("LLAMA_CLOUD_API_KEY")
    openai_api_key: str = os.getenv("OPENAI_API_KEY")
    hf_api_key: str = os.getenv("HF_API_KEY", "")

    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    max_file_size_mb: int = 100
    
    audio: AudioProcessingSettings = AudioProcessingSettings()
    content: ContentProcessingSettings = ContentProcessingSettings()
    vector: VectorProcessingSettings = VectorProcessingSettings()
    generation: QuestionGenerationSettings = QuestionGenerationSettings()
    chunk: ChunkSettings = ChunkSettings()
    rag: RAGSettings = RAGSettings()
    database: DatabaseSettings = DatabaseSettings()
    storage: StorageSettings = StorageSettings()
    minio: MinIOSettings = MinIOSettings()
    
    class Config:
        case_sensitive = False

settings = Settings()

def current_date_time():
    return datetime.now(timezone.utc)