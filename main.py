import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.database import init_db
from app.api import parse_routes, quiz_routes, summary_routes
from app.config import settings
import logging
import asyncio
from contextlib import asynccontextmanager

# Setup logging


import logging
import os

def setup_logging():
    """Setup application logging"""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format=log_format,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("app.log") if os.getenv("LOG_TO_FILE", ) else None
        ]
    )
    
    # Set specific logger levels
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting Document Processing Monolith with RAG capabilities...")
    await init_db()
    
    # Initialize vector service if enabled
    if settings.enable_vector_search:
        try:
            from app.services.vector_service import vector_service
            logger.info(f"Vector service initialized with model: {settings.embedding_model}")
        except Exception as e:
            logger.error(f"Failed to initialize vector service: {e}")
            if settings.enable_rag_generation:
                logger.warning("RAG generation disabled due to vector service failure")
    
    # Validate database connection
    try:
        from app.database import get_db
        from sqlalchemy import text
        db = next(get_db())
        db.execute(text("SELECT 1"))
        logger.info("Database connection validated")
        
        # Check if pgvector extension is available
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
    
    # Shutdown
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

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Global exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": "internal_error"}
    )

# Include all route modules
app.include_router(parse_routes.router, prefix="/parse", tags=["Document Parsing"])
app.include_router(quiz_routes.router, prefix="/quiz", tags=["Quiz Generation"])
app.include_router(summary_routes.router, prefix="/summary", tags=["Document Summarization"])

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
    
    # Check database connection
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
    
    # Check vector service if enabled
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
    """Get current configuration (non-sensitive values only)"""
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

@app.get("/metrics")
async def get_metrics():
    """Get application metrics"""
    if not settings.enable_metrics:
        raise HTTPException(status_code=404, detail="Metrics not enabled")
    
    try:
        from app.database import get_db
        from app.models import Document, Question, Flashcard, QuestionGeneration, DocumentChunk
        from sqlalchemy import text, func
        
        db = next(get_db())
        
        # Document metrics
        doc_count = db.query(func.count(Document.id)).scalar()
        doc_with_embeddings = db.query(func.count(Document.id)).filter(
            Document.processing_status == "completed"
        ).scalar()
        
        # Question metrics
        question_count = db.query(func.count(Question.id)).scalar()
        validated_questions = db.query(func.count(Question.id)).filter(
            Question.human_validated == True
        ).scalar()
        
        # Flashcard metrics
        flashcard_count = db.query(func.count(Flashcard.id)).scalar()
        validated_flashcards = db.query(func.count(Flashcard.id)).filter(
            Flashcard.human_validated == True
        ).scalar()
        
        # Generation metrics
        generation_count = db.query(func.count(QuestionGeneration.id)).scalar()
        completed_generations = db.query(func.count(QuestionGeneration.id)).filter(
            QuestionGeneration.generation_status == "completed"
        ).scalar()
        
        # Vector metrics
        chunk_count = 0
        if settings.enable_vector_search:
            try:
                chunk_count = db.query(func.count(DocumentChunk.id)).scalar()
            except:
                pass
        
        # Quality metrics
        avg_question_score = db.query(func.avg(Question.validation_score)).filter(
            Question.validation_score.isnot(None)
        ).scalar() or 0
        
        avg_flashcard_score = db.query(func.avg(Flashcard.validation_score)).filter(
            Flashcard.validation_score.isnot(None)
        ).scalar() or 0
        
        db.close()
        
        return {
            "documents": {
                "total": doc_count,
                "with_embeddings": doc_with_embeddings,
                "processing_rate": (doc_with_embeddings / doc_count * 100) if doc_count > 0 else 0
            },
            "questions": {
                "total": question_count,
                "validated": validated_questions,
                "validation_rate": (validated_questions / question_count * 100) if question_count > 0 else 0,
                "average_quality_score": round(float(avg_question_score), 2)
            },
            "flashcards": {
                "total": flashcard_count,
                "validated": validated_flashcards,
                "validation_rate": (validated_flashcards / flashcard_count * 100) if flashcard_count > 0 else 0,
                "average_quality_score": round(float(avg_flashcard_score), 2)
            },
            "generations": {
                "total": generation_count,
                "completed": completed_generations,
                "success_rate": (completed_generations / generation_count * 100) if generation_count > 0 else 0
            },
            "vector_chunks": chunk_count
        }
        
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving metrics")

# Development routes
if settings.log_level.upper() == "DEBUG":
    @app.get("/debug/test-vector-search")
    async def test_vector_search():
        """Test vector search functionality"""
        if not settings.enable_vector_search:
            raise HTTPException(status_code=400, detail="Vector search not enabled")
        
        try:
            from app.services.vector_service import vector_service
            from app.database import get_db
            
            db = next(get_db())
            
            # Test embedding creation
            test_texts = ["This is a test document", "Another test sentence"]
            embeddings = vector_service.create_embeddings(test_texts)
            
            db.close()
            
            return {
                "status": "success",
                "embedding_dimension": len(embeddings[0]),
                "test_embeddings_count": len(embeddings)
            }
            
        except Exception as e:
            logger.error(f"Vector search test failed: {e}")
            raise HTTPException(status_code=500, detail=f"Vector search test failed: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=9000, 
        reload=True,
        log_level=settings.log_level.lower()
    )