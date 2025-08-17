from app.api import document_routes
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import logging
from app.database import init_db
from app.api import question_routes
from app.config import settings
from contextlib import asynccontextmanager
from app.database import get_db


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Document Processing Monolith with RAG capabilities...")
    await init_db()
    
    try:
        from app.processors.vector_processor import vector_processor
        logger.info(f"Vector service initialized with model")
    except Exception as e:
        logger.error(f"Failed to initialize vector service: {e}")
    
    try:
        db = next(get_db())
        db.execute(text("SELECT 1"))
        logger.info("Database connection validated")
        
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

app.include_router(document_routes.router, prefix="/document", tags=["Document Parsing"])
app.include_router(question_routes.router, prefix="/question", tags=["Quiz Generation"])

@app.get("/health")
async def health_check():
    return {"status": "healthy",}


if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=9000, 
        reload=True,
    )