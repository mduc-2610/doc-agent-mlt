import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.database import init_db
from app.api import parse_routes, question_routes
from app.config import settings
import logging
import asyncio
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Starting Document Processing Monolith with RAG capabilities...")
    await init_db()
    
    if settings.enable_vector_search:
        try:
            from app.processors.vector_processor import vector_processor
            logger.info(f"Vector service initialized with model: {settings.embedding_model}")
        except Exception as e:
            logger.error(f"Failed to initialize vector service: {e}")
            if settings.enable_rag_generation:
                logger.warning("RAG generation disabled due to vector service failure")
    
    try:
        from app.database import get_db
        from sqlalchemy import text
        db = next(get_db())
        db.execute(text("SELECT 1"))
        logger.info("Database connection validated")
        
        if settings.enable_vector_search:
            try:
                result = db.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'"))
                if result.fetchone():
                    logger.info("pgvector extension detected")
                else:
                    logger.warning("pgvector extension not found - vector search may not work")
            except Exception as e:
                logger.warning(f"Could not check pgvector extension: {e}")
        
        db.close()
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise
    
    logger.info("Application startup completed")
    
    yield
    
    logger.info("Shutting down Document Processing Monolith...")

app = FastAPI(
    title="Document Processing Monolith with RAG",
    version="2.0.0",
    description="Enhanced document processing with vector search and RAG-based quiz generation",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Global exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": "internal_error"}
    )

app.include_router(parse_routes.router, prefix="/parse", tags=["Document Parsing"])
app.include_router(question_routes.router, prefix="/question", tags=["Quiz Generation"])

@app.get("/health")
async def health_check():
    """Comprehensive health check"""
    status = {
        "status": "healthy",
        "service": "document-processing-monolith-rag",
        "version": "2.0.0",
        "features": {
            "vector_search": settings.enable_vector_search,
            "rag_generation": settings.enable_rag_generation,
            "quality_validation": settings.enable_quality_validation,
            "human_review": settings.enable_human_review_workflow
        }
    }
    
    try:
        from app.database import get_db
        from sqlalchemy import text
        db = next(get_db())
        db.execute(text("SELECT 1"))
        db.close()
        status["database"] = "connected"
    except Exception as e:
        status["database"] = f"error: {str(e)}"
        status["status"] = "degraded"
    
    if settings.enable_vector_search:
        try:
            from app.services.vector_service import vector_service
            status["vector_service"] = {
                "model": settings.embedding_model,
                "dimension": settings.embedding_dimension,
                "status": "ready"
            }
        except Exception as e:
            status["vector_service"] = f"error: {str(e)}"
            status["status"] = "degraded"
    
    return status

@app.get("/config")
async def get_config():
    return {
        "embedding_model": settings.embedding_model,
        "embedding_dimension": settings.embedding_dimension,
        "max_context_length": settings.max_context_length,
        "default_quiz_count": settings.default_quiz_count,
        "default_flashcard_count": settings.default_flashcard_count,
        "min_quality_score": settings.min_quality_score,
        "features": {
            "vector_search": settings.enable_vector_search,
            "rag_generation": settings.enable_rag_generation,
            "quality_validation": settings.enable_quality_validation,
            "human_review": settings.enable_human_review_workflow
        }
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=9000, 
        reload=True,
        log_level=settings.log_level.lower()
    )