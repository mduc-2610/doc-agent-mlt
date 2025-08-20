# app/database.py - Enhanced database configuration
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy import text
import logging
from app.config import settings
from app.models import Base, engine, SessionLocal

logger = logging.getLogger(__name__)

# Connection event listeners for monitoring
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Set database-specific optimizations"""
    if 'sqlite' in settings.database.database_url:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    """Log connection checkout for monitoring"""
    logger.debug("Connection checked out from pool")

@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_connection, connection_record):
    """Log connection checkin for monitoring"""
    logger.debug("Connection returned to pool")

class DatabaseManager:
    """Enhanced database management with monitoring and optimization"""
    
    def __init__(self):
        self.engine = engine
        self.SessionLocal = SessionLocal
        self.connection_stats = {
            "total_connections": 0,
            "active_connections": 0,
            "failed_connections": 0
        }
    
    async def init_db(self):
        """Initialize database with enhanced error handling"""
        try:
            logger.info("Initializing database...")
            Base.metadata.create_all(bind=self.engine)
            
            # Test connection
            with self.get_db_session() as db:
                db.execute(text("SELECT 1"))
            
            logger.info("Database initialized successfully")
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    def get_db_session(self) -> Session:
        """Get database session with enhanced error handling"""
        try:
            self.connection_stats["total_connections"] += 1
            session = self.SessionLocal()
            self.connection_stats["active_connections"] += 1
            return session
            
        except Exception as e:
            self.connection_stats["failed_connections"] += 1
            logger.error(f"Failed to create database session: {e}")
            raise
    
    def close_db_session(self, session: Session):
        """Safely close database session"""
        try:
            if session:
                session.close()
                self.connection_stats["active_connections"] = max(0, self.connection_stats["active_connections"] - 1)
        except Exception as e:
            logger.warning(f"Error closing database session: {e}")
    
    def get_connection_stats(self) -> dict:
        """Get database connection statistics"""
        pool = self.engine.pool
        return {
            **self.connection_stats,
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            # "invalid": pool.invalid()
        }
    
    def health_check(self) -> dict:
        """Perform database health check"""
        try:
            with self.get_db_session() as db:
                result = db.execute(text("SELECT 1")).scalar()
                
            return {
                "status": "healthy",
                "connection_successful": result == 1,
                "stats": self.get_connection_stats()
            }
            
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "stats": self.get_connection_stats()
            }

# Global database manager instance
db_manager = DatabaseManager()


# Batch operations for better performance
class BatchOperations:
    """Helper class for efficient batch database operations"""
    
    @staticmethod
    def bulk_insert_questions(db: Session, questions_data: list) -> int:
        """Bulk insert questions for better performance"""
        try:
            from app.models import Question
            
            db.bulk_insert_mappings(Question, questions_data)
            db.commit()
            logger.info(f"Bulk inserted {len(questions_data)} questions")
            return len(questions_data)
            
        except Exception as e:
            db.rollback()
            logger.error(f"Bulk insert questions failed: {e}")
            raise
    
    @staticmethod
    def bulk_insert_flashcards(db: Session, flashcards_data: list) -> int:
        """Bulk insert flashcards for better performance"""
        try:
            from app.models import Flashcard
            
            db.bulk_insert_mappings(Flashcard, flashcards_data)
            db.commit()
            logger.info(f"Bulk inserted {len(flashcards_data)} flashcards")
            return len(flashcards_data)
            
        except Exception as e:
            db.rollback()
            logger.error(f"Bulk insert flashcards failed: {e}")
            raise
    
    @staticmethod
    def bulk_update_processing_status(db: Session, document_ids: list, status: str) -> int:
        """Bulk update document processing status"""
        try:
            from app.models import Document
            from sqlalchemy import update
            
            stmt = update(Document).where(
                Document.id.in_(document_ids)
            ).values(processing_status=status)
            
            result = db.execute(stmt)
            db.commit()
            
            updated_count = result.rowcount
            logger.info(f"Bulk updated {updated_count} documents to status: {status}")
            return updated_count
            
        except Exception as e:
            db.rollback()
            logger.error(f"Bulk update processing status failed: {e}")
            raise

# Database optimization utilities
class DatabaseOptimizer:
    """Utilities for database optimization and maintenance"""
    
    @staticmethod
    def analyze_query_performance(db: Session, query: str) -> dict:
        """Analyze query performance (PostgreSQL specific)"""
        try:
            if 'postgresql' not in settings.database.database_url:
                return {"message": "Query analysis only available for PostgreSQL"}
            
            explain_query = f"EXPLAIN ANALYZE {query}"
            result = db.execute(explain_query).fetchall()
            
            return {
                "query": query,
                "execution_plan": [row[0] for row in result]
            }
            
        except Exception as e:
            logger.error(f"Query analysis failed: {e}")
            return {"error": str(e)}
    
    @staticmethod
    def get_table_stats(db: Session) -> dict:
        """Get table statistics for monitoring"""
        try:
            from app.models import Document, DocumentChunk, Question, Flashcard, Session
            
            stats = {}
            
            for model in [Document, DocumentChunk, Question, Flashcard, Session]:
                table_name = model.__tablename__
                count = db.query(model).count()
                stats[table_name] = {"count": count}
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get table stats: {e}")
            return {"error": str(e)}
    
    @staticmethod
    def cleanup_orphaned_chunks(db: Session) -> int:
        """Remove orphaned document chunks"""
        try:
            from app.models import DocumentChunk, Document
            from sqlalchemy import text
            
            # Find chunks without corresponding documents
            cleanup_query = text("""
                DELETE FROM document_chunks 
                WHERE document_id NOT IN (SELECT id FROM documents)
            """)
            
            result = db.execute(cleanup_query)
            db.commit()
            
            cleaned_count = result.rowcount
            logger.info(f"Cleaned up {cleaned_count} orphaned chunks")
            return cleaned_count
            
        except Exception as e:
            db.rollback()
            logger.error(f"Cleanup failed: {e}")
            raise

# Initialize database on module import
async def init_db():
    """Initialize database"""
    await db_manager.init_db()

# Enhanced dependency for FastAPI
def get_db():
    """Enhanced database dependency with proper cleanup"""
    db = db_manager.get_db_session()
    try:
        yield db
        # Commit any pending transactions
        db.commit()
    except Exception as e:
        # Rollback on any exception
        db.rollback()
        logger.error(f"Database transaction rolled back: {e}")
        raise
    finally:
        # Always close the session
        db_manager.close_db_session(db)
