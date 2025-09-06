from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.summary_service import summary_service
from app.schemas.message import MessageResponse
from app.schemas.document import DocumentSummaryResponse

router = APIRouter()

@router.get("/document/{document_id}", response_model=DocumentSummaryResponse)
async def get_document_summary(document_id: str, db: Session = Depends(get_db)):
    summary = summary_service.get_document_summary(db, document_id)
    if not summary:
        raise HTTPException(
            status_code=404, 
            detail=MessageResponse.create(
                translation_key="documentSummaryNotFound",
                message="Document summary not found"
            ).model_dump()
        )
    
    return DocumentSummaryResponse.model_validate(summary)

@router.post("/document/{document_id}", response_model=DocumentSummaryResponse)
async def generate_document_summary(document_id: str, db: Session = Depends(get_db)):
    try:
        summary = summary_service.generate_document_summary(db, document_id)
        return DocumentSummaryResponse.model_validate(summary)
    except ValueError as e:
        raise HTTPException(
            status_code=400, 
            detail=MessageResponse.create(
                translation_key="invalidSummaryRequest",
                message="Invalid summary request"
            ).model_dump()
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=MessageResponse.create(
                translation_key="summaryGenerationFailed",
                message="Failed to generate summary"
            ).model_dump()
        )
