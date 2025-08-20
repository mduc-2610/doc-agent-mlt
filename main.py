# main.py -  main application
import uvicorn
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import logging
from contextlib import asynccontextmanager
import asyncio
import signal
import sys

# Import enhanced components
from app.database import db_manager, DatabaseOptimizer
from app.api import (
    document_routes,
    question_routes,
    summary_routes,
)
from app.config import settings
from app.services.monitoring_service import monitoring_service, MonitoringMiddleware
from app.services.caching_service import caching_service
from app.processors.vector_processor import vector_processor
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    
# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format=settings.log_format,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log") if hasattr(logging, 'FileHandler') else logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ApplicationManager:
    """Manages application lifecycle and health"""
    
    def __init__(self):
        self.startup_complete = False
        self.shutdown_initiated = False
        self.background_tasks = []
    
    async def startup_sequence(self):
        """ startup sequence with comprehensive initialization"""
        try:
            logger.info("=== Starting Document Processing Application with  RAG ===")
            
            # 1. Initialize database
            logger.info("Initializing database...")
            await db_manager.init_db()
            
            # Verify database health
            health_check = db_manager.health_check()
            if health_check["status"] != "healthy":
                raise Exception(f"Database health check failed: {health_check}")
            logger.info("Database initialized and healthy")
            
            # 2. Check pgvector extension
            try:
                with db_manager.get_db_session() as db:
                    result = db.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'"))
                    if result.fetchone():
                        logger.info("pgvector extension detected")
                    else:
                        logger.warning("pgvector extension not found - vector search may not work")
            except Exception as e:
                logger.warning(f"Could not check pgvector extension: {e}")
            
            # 3. Initialize vector processor
            try:
                # Test embedding model
                test_embeddings = vector_processor.create_embeddings(["test"])
                if test_embeddings and len(test_embeddings[0]) == settings.rag.embedding_dimension:
                    logger.info(f"Vector processor initialized with {settings.rag.embedding_model_name}")
                else:
                    raise Exception("Embedding test failed")
            except Exception as e:
                logger.error(f"Failed to initialize vector processor: {e}")
                raise
            
            # 4. Initialize caching service
            try:
                cache_stats = caching_service.get_stats()
                logger.info(f"Caching service initialized: {cache_stats}")
            except Exception as e:
                logger.warning(f"Caching service initialization warning: {e}")
            
            # 5. Start monitoring service
            try:
                monitoring_service.start_monitoring()
                logger.info("Monitoring service started")
            except Exception as e:
                logger.warning(f"Monitoring service startup warning: {e}")
            
            # 6. Perform initial cleanup
            try:
                cleanup_stats = caching_service.cleanup()
                logger.info(f"Initial cleanup completed: {cleanup_stats}")
                
                # Database cleanup
                with db_manager.get_db_session() as db:
                    cleanup_count = DatabaseOptimizer.cleanup_orphaned_chunks(db)
                    if cleanup_count > 0:
                        logger.info(f"Cleaned up {cleanup_count} orphaned chunks")
            except Exception as e:
                logger.warning(f"Cleanup warning: {e}")
            
            # 7. Schedule background tasks
            self._schedule_background_tasks()
            
            self.startup_complete = True
            logger.info("=== Application startup completed successfully ===")
            
        except Exception as e:
            logger.error(f"Application startup failed: {e}")
            raise
    
    async def shutdown_sequence(self):
        """ shutdown sequence"""
        if self.shutdown_initiated:
            return
        
        self.shutdown_initiated = True
        logger.info("=== Starting application shutdown ===")
        
        try:
            # 1. Cancel background tasks
            for task in self.background_tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            logger.info("Background tasks cancelled")
            
            # 2. Stop monitoring
            try:
                monitoring_service.stop_monitoring()
                logger.info("Monitoring service stopped")
            except Exception as e:
                logger.warning(f"Error stopping monitoring: {e}")
            
            # 3. Final cache cleanup
            try:
                cleanup_stats = caching_service.cleanup()
                logger.info(f"Final cache cleanup: {cleanup_stats}")
            except Exception as e:
                logger.warning(f"Cache cleanup error: {e}")
            
            # 4. Get final statistics
            try:
                final_stats = monitoring_service.get_comprehensive_stats()
                logger.info(f"Final application statistics collected")
                # In production, you might want to send these to an external service
            except Exception as e:
                logger.warning(f"Error collecting final stats: {e}")
            
            logger.info("=== Application shutdown completed ===")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    def _schedule_background_tasks(self):
        """Schedule background maintenance tasks"""
        # Cache cleanup task
        async def cache_cleanup_task():
            while not self.shutdown_initiated:
                try:
                    await asyncio.sleep(3600)  # Every hour
                    if not self.shutdown_initiated:
                        cleanup_stats = caching_service.cleanup()
                        logger.debug(f"Scheduled cache cleanup: {cleanup_stats}")
                except Exception as e:
                    logger.warning(f"Cache cleanup task error: {e}")
        
        # Database maintenance task
        async def db_maintenance_task():
            while not self.shutdown_initiated:
                try:
                    await asyncio.sleep(86400)  # Every 24 hours
                    if not self.shutdown_initiated:
                        with db_manager.get_db_session() as db:
                            cleanup_count = DatabaseOptimizer.cleanup_orphaned_chunks(db)
                            logger.info(f"Daily DB maintenance: cleaned {cleanup_count} orphaned chunks")
                except Exception as e:
                    logger.warning(f"DB maintenance task error: {e}")
        
        # Start background tasks
        self.background_tasks.append(asyncio.create_task(cache_cleanup_task()))
        self.background_tasks.append(asyncio.create_task(db_maintenance_task()))
        logger.info("Background maintenance tasks scheduled")

# Global application manager
app_manager = ApplicationManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """ application lifespan management"""
    
    # Startup
    await app_manager.startup_sequence()
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        asyncio.create_task(app_manager.shutdown_sequence())
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        yield
    finally:
        # Shutdown
        await app_manager.shutdown_sequence()

# Create FastAPI application with enhanced configuration
app = FastAPI(
    title=" Document Processing with RAG",
    version="2.1.0",
    description="""
     document processing system with advanced RAG capabilities:
    
    ✨ **Features:**
    - Hybrid search (semantic + keyword)
    - Multi-level caching system
    - Comprehensive monitoring
    - Batch processing
    -  error handling
    - Performance optimization
    
    📊 **Supported Content:**
    - Documents: PDF, DOCX, Images
    - Media: Audio, Video, YouTube
    - Web: URLs, Web scraping
    
    🔧 **Capabilities:**
    - RAG-based quiz generation
    - Flashcard creation
    - Session management
    - Content summarization
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add monitoring middleware
app.add_middleware(MonitoringMiddleware, monitoring_service=monitoring_service)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(document_routes.router, prefix="/document", tags=["📄 Document Processing"])
app.include_router(question_routes.router, prefix="/question", tags=["❓ Quiz & Flashcard Generation"])
app.include_router(summary_routes.router, prefix="/summary", tags=["📝 Content Summarization"])

#  health and monitoring endpoints
@app.get("/health", tags=["🔧 System"])
async def health_check():
    """Comprehensive health check endpoint"""
    return monitoring_service.get_health_status()

@app.get("/health/detailed", tags=["🔧 System"])
async def detailed_health_check():
    """Detailed health check with comprehensive metrics"""
    return monitoring_service.get_comprehensive_stats()

@app.get("/metrics", tags=["🔧 System"])
async def get_metrics():
    """Get application metrics and statistics"""
    return {
        "monitoring": monitoring_service.get_comprehensive_stats(),
        "database": db_manager.get_connection_stats(),
        "caching": caching_service.get_stats(),
        "vector_processor": vector_processor.get_cache_stats()
    }

@app.get("/performance", tags=["🔧 System"])
async def get_performance_stats():
    """Get performance-focused statistics"""
    return {
        "system_health": monitoring_service.get_health_status(),
        "cache_performance": caching_service.get_stats(),
        "database_stats": db_manager.get_connection_stats(),
        "recent_errors": monitoring_service.app_monitor.get_error_summary(hours=1)
    }

@app.post("/admin/cache/clear", tags=["🔧 System"])
async def clear_caches():
    """Clear all caches (admin endpoint)"""
    try:
        cache_stats = caching_service.cleanup()
        vector_cache_stats = vector_processor.cleanup_cache()
        
        return {
            "message": "Caches cleared successfully",
            "cache_entries_removed": cache_stats,
            "vector_cache_entries_removed": vector_cache_stats
        }
    except Exception as e:
        logger.error(f"Cache clear failed: {e}")
        return {"error": str(e)}

@app.get("/admin/database/stats", tags=["🔧 System"])
async def get_database_stats():
    """Get detailed database statistics (admin endpoint)"""
    try:
        with db_manager.get_db_session() as db:
            stats = DatabaseOptimizer.get_table_stats(db)
        
        return {
            "connection_stats": db_manager.get_connection_stats(),
            "table_stats": stats,
            "health": db_manager.health_check()
        }
    except Exception as e:
        logger.error(f"Database stats failed: {e}")
        return {"error": str(e)}

@app.post("/admin/database/cleanup", tags=["🔧 System"])
async def cleanup_database():
    """Cleanup orphaned database entries (admin endpoint)"""
    try:
        with db_manager.get_db_session() as db:
            cleanup_count = DatabaseOptimizer.cleanup_orphaned_chunks(db)
        
        return {
            "message": "Database cleanup completed",
            "orphaned_chunks_removed": cleanup_count
        }
    except Exception as e:
        logger.error(f"Database cleanup failed: {e}")
        return {"error": str(e)}

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    monitoring_service.record_error("not_found", str(request.url.path))
    return {"error": "Resource not found", "path": str(request.url.path)}

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    monitoring_service.record_error("internal_error", str(request.url.path), str(exc))
    logger.error(f"Internal error on {request.url.path}: {exc}")
    return {"error": "Internal server error", "message": "Please contact support if this persists"}

if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=9000, 
        reload=False,  # Disable reload in production
        workers=1,     # Single worker for now, can be increased
        access_log=True,
        log_level=settings.log_level.lower()
    )