

from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession, joinedload

class TutorChatMessage(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant)$")
    content: str


class TutorChatRequest(BaseModel):
    session_id: str
    user_id: str
    message: str
    question_id: Optional[str] = None
    flashcard_id: Optional[str] = None
    document_ids: Optional[List[str]] = None
    history: Optional[List[TutorChatMessage]] = None
    top_k: int = 6
    response_style: Optional[str] = None


class TutorChatResponse(BaseModel):
    reply: str
    citations: List[Dict[str, str]]
    used_context: str
    next_suggestions: List[str]


class TutorExplainResponse(TutorChatResponse):
    question_id: str