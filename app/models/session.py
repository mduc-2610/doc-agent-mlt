from sqlalchemy import Column, String, Text, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.config import current_date_time
from .base import Base

class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=current_date_time)
    updated_at = Column(DateTime, default=current_date_time, onupdate=current_date_time)
    total_documents = Column(Integer, default=0) 
