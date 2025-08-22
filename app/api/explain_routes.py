from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.explain import QuizExplainRequest, QuizExplainResponse, QuizExplainResult
from app.services.explain_service import explain_service

router = APIRouter()

@router.post("/explain", response_model=QuizExplainResponse)
def explain_quiz(req: QuizExplainRequest, db: Session = Depends(get_db)):
    out = explain_service.explain(
        db=db,
        session_id=req.session_id,
        stem=req.stem,
        options=req.options or None,
    )
    if out["mode"] == "ok":
        return QuizExplainResponse(mode="ok", result=QuizExplainResult(**out["result"]))
    return QuizExplainResponse(**out)
