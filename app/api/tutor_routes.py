import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession, joinedload

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.tutor import (
    TutorChatRequest,
    TutorChatResponse,
    TutorExplainResponse
)
from app.config import settings
from app.database import get_db  
from app.services.tutor_service import tutor_service

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/explain/{question_id}", response_model=TutorExplainResponse)
def explain_question_endpoint(
    question_id: str,
    user_message: str = "Please explain this question and how to solve it.",
    top_k: int = 6,
    db: OrmSession = Depends(get_db),
):
    return tutor_service.explain_question(db, question_id, user_message=user_message, top_k=top_k)

@router.post("/chat", response_model=TutorChatResponse)
def chat_endpoint(req: TutorChatRequest, db: OrmSession = Depends(get_db)):
    return tutor_service.chat(db, req)

# Optional: convenience to purge the small local cache
@router.delete("/cache")
def clear_cache():
    n = tutor_service.agent.clear_cache()
    return {"cleared": n}
