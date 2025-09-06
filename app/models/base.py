from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import QueuePool
from sqlalchemy.orm import sessionmaker
from app.config import settings


from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import QueuePool
from sqlalchemy.orm import sessionmaker
from app.config import settings


engine = create_engine(
    settings.database.get_database_url(),
    poolclass=QueuePool,
    pool_size=settings.database.pool_size,
    max_overflow=settings.database.max_overflow,
    pool_timeout=settings.database.pool_timeout,
    pool_recycle=settings.database.pool_recycle,
    echo=settings.database.echo,
    pool_pre_ping=True,  
    pool_reset_on_return='commit',  
    # Additional PostgreSQL optimizations
    connect_args={
        "options": "-c timezone=utc",
        "application_name": "doc_agent_app"
    } if "postgresql" in settings.database.get_database_url() else {}
)

SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine
)
Base = declarative_base()