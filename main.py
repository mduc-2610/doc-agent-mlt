import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
import logging
import os
from contextlib import asynccontextmanager
import sys
from app.database import init_db, get_db
from app.api import (
    document_routes, 
    session_routes,
    question_routes,
    summary_routes,
)
from app.config import settings
from app.processors.vector_processor import vector_processor
from app.database import SessionLocal

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format=settings.log_format,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== Starting Document Processing Application ===")
    
    try:
        logger.info("Initializing database...")
        await init_db()
        logger.info("Database initialized successfully")
        
        test_embeddings = vector_processor.create_embeddings(["test"])
        if test_embeddings and len(test_embeddings[0]) == settings.rag.embedding_dimension:
            logger.info(f"Vector processor initialized with {settings.rag.embedding_model_name}")
        else:
            logger.warning("Vector processor test failed")
        
        logger.info("=== Application startup completed ===")
        
    except Exception as e:
        logger.error(f"Application startup failed: {e}")
        raise
    
    try:
        yield
    finally:
        logger.info("=== Application shutdown ===")
        try:
            cache_cleared = vector_processor.cleanup_cache()
            logger.info(f"Cleared {cache_cleared} cached embeddings")
        except Exception as e:
            logger.warning(f"Cache cleanup error: {e}")
        logger.info("=== Shutdown completed ===")

app = FastAPI(title="Document Processing with RAG", version="2.0.0", lifespan=lifespan)

app.mount(f"/{settings.storage.local_path}", StaticFiles(directory=settings.storage.local_path), name=f"{settings.storage.local_path}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(document_routes.router, prefix="/api/agent/document", tags=["Document Processing"])
app.include_router(session_routes.router, prefix="/api/agent/session", tags=["Session Management"])
app.include_router(question_routes.router, prefix="/api/agent/question", tags=["Quiz & Flashcard Generation"])
app.include_router(summary_routes.router, prefix="/api/agent/summary", tags=["Document Summary"])

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": "connected",
        "vector_processor": "ready"
    }

@app.get("/cache_stats")
async def get_cache_stats():
    try:
        stats = {
            "cache_stats": vector_processor.get_cache_stats()
        }
        return stats
    except Exception as e:
        logger.error(f"Stats retrieval failed: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000,reload=True, workers=1, access_log=True)