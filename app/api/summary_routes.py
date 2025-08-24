from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.summary_service import summary_service
from app.schemas.document import DocumentSummaryResponse
from app.utils.error_handling import handle_database_errors

router = APIRouter()

@router.get("/document/{document_id}", response_model=DocumentSummaryResponse)
async def get_document_summary(document_id: str, db: Session = Depends(get_db)):
    summary = summary_service.get_document_summary(db, document_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Document summary not found")
    
    return DocumentSummaryResponse.model_validate(summary)

@router.post("/document/{document_id}", response_model=DocumentSummaryResponse)
@handle_database_errors
async def generate_document_summary(document_id: str, db: Session = Depends(get_db)):
    try:
        summary = summary_service.generate_document_summary(db, document_id)
        return DocumentSummaryResponse.model_validate(summary)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {str(e)}")

@router.get("/document/{document_id}/or-generate", response_model=DocumentSummaryResponse)
@handle_database_errors
async def get_or_generate_document_summary(document_id: str, db: Session = Depends(get_db)):
    try:
        summary = summary_service.get_or_generate_document_summary(db, document_id)
        return DocumentSummaryResponse.model_validate(summary)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get or generate summary: {str(e)}")
