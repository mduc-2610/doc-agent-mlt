from pydantic import BaseModel
from typing import List, Dict, Optional, Any

class QuizExplainRequest(BaseModel):
    session_id: str
    stem: str
    options: Optional[List[str]] = None

class QuizExplainResult(BaseModel):
    answer_choice: str = ""
    explanation_bullets: List[str] = []
    why_not: Dict[str, str] = {}
    citations: List[str] = []
    confidence: float = 0.0

class QuizExplainResponse(BaseModel):
    mode: str
    result: Optional[QuizExplainResult] = None
    message: Optional[str] = None
    raw: Optional[str] = None
    note: Optional[str] = None
