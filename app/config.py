import os
from datetime import datetime, timezone
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv(override=True)

class Settings(BaseSettings):
    # Database configuration
    database_url: str = os.getenv("DATABASE_URL")
    
    # API Keys
    llama_cloud_api_key: str = os.getenv("LLAMA_CLOUD_API_KEY")
    openai_api_key: str = os.getenv("OPENAI_API_KEY")
    hf_api_key: str = os.getenv("HF_API_KEY", "")
    
    # File storage
    content_files_dir: str = "content_files"
    temp_files_dir: str = "tmp_dir"
    
    # Vector search configuration
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5")
    embedding_dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "1024"))
    vector_similarity_threshold: float = float(os.getenv("VECTOR_SIMILARITY_THRESHOLD", "0.7"))
    max_context_length: int = int(os.getenv("MAX_CONTEXT_LENGTH", "4000"))
    
    # Generation configuration
    default_quiz_count: int = int(os.getenv("DEFAULT_QUIZ_COUNT", "15"))
    default_flashcard_count: int = int(os.getenv("DEFAULT_FLASHCARD_COUNT", "15"))
    default_target_chunks: int = int(os.getenv("DEFAULT_TARGET_CHUNKS", "10"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
    
    # Quality control
    min_quality_score: float = float(os.getenv("MIN_QUALITY_SCORE", "0.6"))
    require_human_review: bool = os.getenv("REQUIRE_HUMAN_REVIEW", "false").lower() == "true"
    auto_approve_threshold: float = float(os.getenv("AUTO_APPROVE_THRESHOLD", "0.8"))
    
    # Performance settings
    batch_size: int = int(os.getenv("BATCH_SIZE", "10"))
    max_concurrent_requests: int = int(os.getenv("MAX_CONCURRENT_REQUESTS", "5"))
    cache_embeddings: bool = os.getenv("CACHE_EMBEDDINGS", "true").lower() == "true"
    
    # Monitoring and logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    enable_metrics: bool = os.getenv("ENABLE_METRICS", "false").lower() == "true"
    metrics_port: int = int(os.getenv("METRICS_PORT", "8001"))
    
    # MLFlow configuration (optional)
    mlflow_tracking_uri: str = os.getenv("MLFLOW_TRACKING_URI", "")
    mlflow_experiment_name: str = os.getenv("MLFLOW_EXPERIMENT_NAME", "quiz_generation")
    
    # LLM Configuration
    llm_model: str = os.getenv("LLM_MODEL", "deepseek/deepseek-r1-0528:free")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "2000"))
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    
    # Feature flags
    enable_vector_search: bool = os.getenv("ENABLE_VECTOR_SEARCH", "true").lower() == "true"
    enable_rag_generation: bool = os.getenv("ENABLE_RAG_GENERATION", "true").lower() == "true"
    enable_quality_validation: bool = os.getenv("ENABLE_QUALITY_VALIDATION", "true").lower() == "true"
    enable_human_review_workflow: bool = os.getenv("ENABLE_HUMAN_REVIEW_WORKFLOW", "false").lower() == "true"
    
    class Config:
        case_sensitive = False

settings = Settings()

def current_date_time():
    return datetime.now(timezone.utc)
