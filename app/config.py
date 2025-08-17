import os
from datetime import datetime, timezone
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv(override=True)

class Settings(BaseSettings):
    database_url: str = os.getenv("DATABASE_URL")
    
    llama_cloud_api_key: str = os.getenv("LLAMA_CLOUD_API_KEY")
    openai_api_key: str = os.getenv("OPENAI_API_KEY")
    hf_api_key: str = os.getenv("HF_API_KEY", "")
    
    content_files_dir: str = "content_files"
    temp_files_dir: str = "tmp_dir"
    
    class Config:
        case_sensitive = False

settings = Settings()

def current_date_time():
    return datetime.now(timezone.utc)
