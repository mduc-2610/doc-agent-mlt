from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.services import summarize_service
import traceback

router = APIRouter()

class SummarizeRequest(BaseModel):
    document_id: str
    target_chunks: int = 5

@router.post("/")
async def summarize_document(request: SummarizeRequest, db: Session = Depends(get_db)):
    try:
        summary = summarize_service.create_summary(db, request.document_id, request.target_chunks)
        
        return {
            "document_id": request.document_id,
            "summary_id": str(summary.id),
            "original_word_count": summary.original_word_count,
            "num_chunks": summary.num_chunks,
            "chunk_summaries": summary.chunk_summaries,
            "global_summary": summary.global_summary,
            "created_at": summary.created_at
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{summary_id}")
async def get_summary(summary_id: str, db: Session = Depends(get_db)):
    try:
        summary = summarize_service.get_summary(db, summary_id)
        if not summary:
            raise HTTPException(status_code=404, detail="Summary not found")
        
        return {
            "summary_id": str(summary.id),
            "document_id": str(summary.document_id),
            "original_word_count": summary.original_word_count,
            "num_chunks": summary.num_chunks,
            "chunk_summaries": summary.chunk_summaries,
            "global_summary": summary.global_summary,
            "created_at": summary.created_at
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/by-document/{document_id}")
async def get_summary_by_document(document_id: str, db: Session = Depends(get_db)):
    try:
        summary = summarize_service.get_summary_by_document(db, document_id)
        if not summary:
            raise HTTPException(status_code=404, detail="Summary not found for document")
        
        return {
            "summary_id": str(summary.id),
            "document_id": str(summary.document_id),
            "original_word_count": summary.original_word_count,
            "num_chunks": summary.num_chunks,
            "chunk_summaries": summary.chunk_summaries,
            "global_summary": summary.global_summary,
            "created_at": summary.created_at
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))