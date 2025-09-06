from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import logging
from app.config import settings
from app.models import Base, engine, SessionLocal
logger = logging.getLogger(__name__)

@event.listens_for(engine, "connect")
def set_database_pragma(dbapi_connection, connection_record):
    db_url = settings.database.get_database_url()
    
    if 'sqlite' in db_url:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()
    elif 'postgresql' in db_url:
        cursor = dbapi_connection.cursor()
        cursor.execute("SET timezone TO 'UTC'")
        cursor.execute("SET statement_timeout = '300s'")
        cursor.execute("SET lock_timeout = '30s'")
        cursor.close()
        logger.info("PostgreSQL connection configured successfully")

async def test_db_connection():
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        logger.info(f"Database connection successful: {settings.database.get_database_url()}")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False

async def init_db():
    try:
        logger.info("Testing database connection...")
        
        connection_ok = await test_db_connection()
        if not connection_ok:
            raise Exception("Database connection test failed")
        
        logger.info("Initializing database...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized successfully")
        
        db_url = settings.database.get_database_url()
        if settings.database.use_aws_db:
            logger.info(f"Using AWS PostgreSQL database at: {settings.database.aws_db_host}")
        else:
            logger.info(f"Using local database: {db_url}")
            
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database transaction error: {e}")
        
        if "connection" in str(e).lower() or "timeout" in str(e).lower():
            logger.error("Database connection issue detected. Check your database configuration.")
            if settings.database.use_aws_db:
                logger.error("Verify AWS RDS endpoint, credentials, and security groups.")
        
        raise
    finally:
        db.close()


def bulk_insert_questions(db: Session, questions_data: list) -> int:
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

def bulk_insert_flashcards(db: Session, flashcards_data: list) -> int:
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