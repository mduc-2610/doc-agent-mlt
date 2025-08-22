# app/database.py - Simplified database configuration
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import logging
from app.config import settings
from app.models import Base, engine, SessionLocal

logger = logging.getLogger(__name__)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if 'sqlite' in settings.database.database_url:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

async def init_db():
    try:
        logger.info("Initializing database...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized successfully")
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
        raise
    finally:
        db.close()

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