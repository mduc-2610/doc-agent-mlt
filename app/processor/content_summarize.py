import os
import uuid
import requests
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models import Document, DocumentSummary
from app.config import current_date_time
import traceback
import logging

logger = logging.getLogger(__name__)

class SummarizeService:
    def __init__(self):
        self.ollama_base_url = "http://localhost:11434"
        self.models = {
            "phi3-mini": "phi3:mini",
            "mistral-7b": "mistral:7b"
        }
        self.summary_dir = "content_summary"
        os.makedirs(self.summary_dir, exist_ok=True)
    
    def _make_ollama_request(self, model: str, prompt: str) -> str:
        """Make request to Ollama API"""
        try:
            url = f"{self.ollama_base_url}/api/generate"
            data = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_ctx": 4096 if "phi3" in model else 8192,
                    "temperature": 0.7
                }
            }
            
            response = requests.post(url, json=data, timeout=120)
            response.raise_for_status()
            
            result = response.json()
            return result.get("response", "")
            
        except Exception as e:
            logger.error(f"Ollama request failed: {e}")
            raise HTTPException(status_code=500, detail=f"Summary generation failed: {str(e)}")
    
    def _create_summary_prompt(self, text_content: str) -> str:
        """Create prompt for document summarization"""
        return f"""
Analyze this document and create a summary with exactly these 4 sections:

## Key Terms
[Important terms and definitions]

## Main Ideas  
[Core concepts and topics]

## Important Data
[Facts, statistics, examples]

## Key Takeaways for Exam
[Critical points for studying]

Document:
{text_content}
"""
    
    def _save_summary_to_file(self, summary_text: str, summary_id: str) -> str:
        """Save summary to file"""
        file_path = os.path.join(self.summary_dir, f"{summary_id}.txt")
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(summary_text)
            return file_path
        except Exception as e:
            logger.error(f"Failed to save summary: {e}")
            raise HTTPException(status_code=500, detail="Failed to save summary")
    
    def create_summary(self, db: Session, document_id: str, model_choice: str = "phi3-mini") -> DocumentSummary:
        """Create a summary for a document"""
        try:
            if model_choice not in self.models:
                raise HTTPException(status_code=400, detail=f"Invalid model. Available: {list(self.models.keys())}")
            
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            if not document.content_file_path or not os.path.exists(document.content_file_path):
                raise HTTPException(status_code=404, detail="Document content not found")
            
            with open(document.content_file_path, 'r', encoding='utf-8') as f:
                text_content = f.read()
            
            if not text_content.strip():
                raise HTTPException(status_code=400, detail="Document content is empty")
            
            # Generate summary
            prompt = self._create_summary_prompt(text_content)
            ollama_model = self.models[model_choice]
            summary_text = self._make_ollama_request(ollama_model, prompt)
            
            if not summary_text.strip():
                raise HTTPException(status_code=500, detail="Empty summary generated")
            
            # Save summary
            summary_id = str(uuid.uuid4())
            summary_file_path = self._save_summary_to_file(summary_text, summary_id)
            
            summary_obj = DocumentSummary(
                id=summary_id,
                document_id=document_id,
                summary_file_path=summary_file_path,
                model_used=model_choice,
                original_word_count=len(text_content.split()),
                summary_word_count=len(summary_text.split()),
                created_at=current_date_time()
            )
            
            db.add(summary_obj)
            db.commit()
            db.refresh(summary_obj)
            
            return summary_obj
            
        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    
    def get_summary(self, db: Session, summary_id: str) -> Optional[DocumentSummary]:
        return db.query(DocumentSummary).filter(DocumentSummary.id == summary_id).first()
    
    def get_summaries_by_document(self, db: Session, document_id: str):
        return db.query(DocumentSummary).filter(DocumentSummary.document_id == document_id).all()
    
    def get_summaries_by_session(self, db: Session, session_id: str):
        return db.query(DocumentSummary).join(Document).filter(Document.session_id == session_id).all()
    
    def delete_summary(self, db: Session, summary_id: str):
        try:
            summary = db.query(DocumentSummary).filter(DocumentSummary.id == summary_id).first()
            if not summary:
                raise HTTPException(status_code=404, detail="Summary not found")
            
            if summary.summary_file_path and os.path.exists(summary.summary_file_path):
                os.remove(summary.summary_file_path)
            
            db.delete(summary)
            db.commit()
            
        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))

summary_service = SummarizeService()