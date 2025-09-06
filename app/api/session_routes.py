from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.session_service import session_service
from app.schemas.session import (
    SessionCreateRequest,
    SessionUpdateRequest,
    SessionDetailResponse,
    SessionResponse,
)
from app.schemas.common import MessageResponse
from app.utils.helper import as_form

router = APIRouter()

@router.get("/", response_model=List[SessionResponse])
def get_sessions(db: Session = Depends(get_db)):
    sessions = session_service.get_sessions(db)
    return [SessionResponse.model_validate(s) for s in sessions]

@router.post("/", response_model=SessionResponse)
async def create_session(request: SessionCreateRequest = Depends(as_form(SessionCreateRequest)), db: Session = Depends(get_db)):
    session = session_service.create_session(db, request)
    return SessionResponse.model_validate(session)

@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(session_id: str, db: Session = Depends(get_db)):
    session = session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionDetailResponse.model_validate(session)

@router.get("/user/{user_id}", response_model=List[SessionResponse])
async def get_user_sessions(user_id: str, db: Session = Depends(get_db)):
    sessions = session_service.get_user_sessions(db, user_id)
    return [SessionResponse.model_validate(s) for s in sessions]

@router.put("/{session_id}", response_model=MessageResponse)
async def update_session(session_id: str, request: SessionUpdateRequest = Depends(as_form(SessionUpdateRequest)), db: Session = Depends(get_db)):
    session_service.update_session(db, session_id, request)
    return MessageResponse(message="Session updated successfully")

@router.delete("/{session_id}", response_model=MessageResponse)
async def delete_session(session_id: str, db: Session = Depends(get_db)):
    session_service.delete_session(db, session_id)
    return MessageResponse(message="Deleted successfully")
