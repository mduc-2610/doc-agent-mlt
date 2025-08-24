from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import traceback

from app.schemas.tutor import (
    TutorSessionCreate, TutorSessionResponse, TutorInteractionResponse,
    ExplainConceptRequest, FlashcardStudyRequest, FlashcardStudyResponse,
    QuestionPracticeRequest, QuestionPracticeResponse, UserQuestionRequest,
    TutorResponse, LearningProgressResponse
)
from app.database import get_db
from app.services.tutor_service import tutor_service
from app.utils.error_handling import handle_database_errors, handle_llm_errors

router = APIRouter()

@router.post("/session/create", response_model=TutorSessionResponse)
@handle_database_errors
async def create_tutor_session(
    request: TutorSessionCreate,
    db: Session = Depends(get_db)
):
    """Create a new tutor session"""
    session = tutor_service.create_tutor_session(db, request)
    return TutorSessionResponse.model_validate(session)

@router.get("/session/{session_id}", response_model=TutorSessionResponse)
@handle_database_errors
async def get_tutor_session(
    session_id: str,
    user_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """Get tutor session with interactions"""
    session = tutor_service.get_tutor_session(db, session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tutor session not found")
    return TutorSessionResponse.model_validate(session)

@router.post("/explain", response_model=TutorResponse)
@handle_llm_errors
@handle_database_errors
async def explain_concept(
    request: ExplainConceptRequest,
    db: Session = Depends(get_db)
):
    """Explain a concept using AI tutor"""
    return tutor_service.explain_concept(db, request)

@router.post("/flashcard/study", response_model=FlashcardStudyResponse)
@handle_database_errors
async def start_flashcard_study(
    request: FlashcardStudyRequest,
    db: Session = Depends(get_db)
):
    """Start or continue flashcard study session"""
    return tutor_service.handle_flashcard_study(db, request)

@router.post("/flashcard/{flashcard_id}/reveal", response_model=FlashcardStudyResponse)
@handle_database_errors
async def reveal_flashcard_answer(
    flashcard_id: str,
    user_id: str = Query(...),
    session_id: str = Query(...),
    difficulty_rating: str = Query(..., description="easy, good, hard, again"),
    db: Session = Depends(get_db)
):
    """Reveal flashcard answer and update progress"""
    return tutor_service.reveal_flashcard_answer(
        db, flashcard_id, user_id, session_id, difficulty_rating
    )

@router.post("/question/practice", response_model=QuestionPracticeResponse)
@handle_database_errors
async def start_question_practice(
    request: QuestionPracticeRequest,
    db: Session = Depends(get_db)
):
    """Start or continue question practice session"""
    return tutor_service.handle_question_practice(db, request)

@router.post("/question/{question_id}/answer", response_model=QuestionPracticeResponse)
@handle_database_errors
async def submit_question_answer(
    question_id: str,
    user_answer: str = Query(...),
    user_id: str = Query(...),
    session_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """Submit answer to a practice question"""
    return tutor_service.submit_question_answer(
        db, question_id, user_answer, user_id, session_id
    )

@router.post("/ask", response_model=TutorResponse)
@handle_llm_errors
@handle_database_errors
async def ask_tutor_question(
    request: UserQuestionRequest,
    db: Session = Depends(get_db)
):
    """Ask the AI tutor a custom question"""
    return tutor_service.answer_user_question(db, request)

@router.get("/progress/{session_id}", response_model=LearningProgressResponse)
@handle_database_errors
async def get_learning_progress(
    session_id: str,
    user_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """Get learning progress for a session"""
    progress = tutor_service.get_learning_progress(db, user_id, session_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Learning progress not found")
    return LearningProgressResponse.model_validate(progress)

@router.get("/sessions/{user_id}", response_model=List[TutorSessionResponse])
@handle_database_errors
async def get_user_tutor_sessions(
    user_id: str,
    db: Session = Depends(get_db)
):
    """Get all tutor sessions for a user"""
    from app.models import TutorSession
    from sqlalchemy.orm import joinedload
    
    sessions = (
        db.query(TutorSession)
        .options(joinedload(TutorSession.interactions))
        .filter(TutorSession.user_id == user_id)
        .order_by(TutorSession.updated_at.desc())
        .all()
    )
    
    return [TutorSessionResponse.model_validate(session) for session in sessions]

@router.delete("/session/{session_id}")
@handle_database_errors
async def end_tutor_session(
    session_id: str,
    user_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """End (deactivate) a tutor session"""
    from app.models import TutorSession
    
    session = (
        db.query(TutorSession)
        .filter(
            TutorSession.session_id == session_id,
            TutorSession.user_id == user_id
        )
        .first()
    )
    
    if not session:
        raise HTTPException(status_code=404, detail="Tutor session not found")
    
    session.is_active = False
    db.commit()
    
    return {"message": "Tutor session ended successfully"}

@router.get("/interactions/{session_id}", response_model=List[TutorInteractionResponse])
@handle_database_errors
async def get_session_interactions(
    session_id: str,
    user_id: str = Query(...),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get interactions for a tutor session"""
    from app.models import TutorSession, TutorInteraction
    
    # First verify the tutor session exists and belongs to the user
    tutor_session = (
        db.query(TutorSession)
        .filter(
            TutorSession.session_id == session_id,
            TutorSession.user_id == user_id
        )
        .first()
    )
    
    if not tutor_session:
        raise HTTPException(status_code=404, detail="Tutor session not found")
    
    # Get interactions
    interactions = (
        db.query(TutorInteraction)
        .filter(TutorInteraction.tutor_session_id == tutor_session.id)
        .order_by(TutorInteraction.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    
    return [TutorInteractionResponse.model_validate(interaction) for interaction in interactions]

@router.post("/interaction/{interaction_id}/feedback")
@handle_database_errors
async def provide_interaction_feedback(
    interaction_id: str,
    feedback: str = Query(..., description="helpful, not_helpful, partially_helpful"),
    user_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """Provide feedback on a tutor interaction"""
    from app.models import TutorInteraction, TutorSession
    
    interaction = (
        db.query(TutorInteraction)
        .join(TutorSession)
        .filter(
            TutorInteraction.id == interaction_id,
            TutorSession.user_id == user_id
        )
        .first()
    )
    
    if not interaction:
        raise HTTPException(status_code=404, detail="Interaction not found")
    
    interaction.user_feedback = feedback
    db.commit()
    
    return {"message": "Feedback recorded successfully"}

@router.get("/stats/{session_id}")
@handle_database_errors
async def get_tutor_session_stats(
    session_id: str,
    user_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """Get statistics for a tutor session"""
    from app.models import TutorSession, TutorInteraction
    from sqlalchemy import func
    
    # Verify session exists
    tutor_session = (
        db.query(TutorSession)
        .filter(
            TutorSession.session_id == session_id,
            TutorSession.user_id == user_id
        )
        .first()
    )
    
    if not tutor_session:
        raise HTTPException(status_code=404, detail="Tutor session not found")
    
    # Get interaction statistics
    interaction_stats = (
        db.query(
            TutorInteraction.interaction_type,
            func.count(TutorInteraction.id).label('count')
        )
        .filter(TutorInteraction.tutor_session_id == tutor_session.id)
        .group_by(TutorInteraction.interaction_type)
        .all()
    )
    
    # Get learning progress
    progress = tutor_service.get_learning_progress(db, user_id, session_id)
    
    return {
        "session_id": session_id,
        "tutor_type": tutor_session.tutor_type,
        "interaction_stats": {stat.interaction_type: stat.count for stat in interaction_stats},
        "learning_progress": LearningProgressResponse.model_validate(progress) if progress else None,
        "session_duration_minutes": (tutor_session.updated_at - tutor_session.created_at).total_seconds() / 60,
        "is_active": tutor_session.is_active
    }
