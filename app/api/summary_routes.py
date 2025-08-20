import traceback
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.summary_service import summary_service
from app.schemas.summary import SummaryResponse, SummaryGenerationRequest
from app.schemas.document import MessageResponse
from app.utils.helper import as_form
from app.utils.error_handling import handle_database_errors

router = APIRouter()

@router.get("/session/{session_id}", response_model=SummaryResponse)
@handle_database_errors
async def get_session_summary(session_id: str, db: Session = Depends(get_db)):
    """Get the summary for a specific session"""
    summary = summary_service.get_session_summary(db, session_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found for this session")
    
    return SummaryResponse.model_validate(summary)

@router.post("/generate/{session_id}/", response_model=SummaryResponse)
@handle_database_errors
async def generate_session_summary(
    session_id: str,
    request: SummaryGenerationRequest = Depends(as_form(SummaryGenerationRequest)),
    db: Session = Depends(get_db)
):
    if request.session_id != session_id:
        raise HTTPException(status_code=400, detail="Session ID mismatch")
    
    summary = summary_service.generate_or_update_summary(
        db, 
        session_id, 
        regenerate=request.regenerate
    )
    
    return SummaryResponse.model_validate(summary)

@router.delete("/session/{session_id}", response_model=MessageResponse)
@handle_database_errors
async def delete_session_summary(session_id: str, db: Session = Depends(get_db)):
    """Delete summary for a session"""
    summary_service.delete_session_summary(db, session_id)
    return MessageResponse(message="Summary deleted successfully")