from sqlalchemy.orm import Session
from app.models.document import Document, DocumentSummary
from app.utils.template import SUMMARY_GENERATION_PROMPT_TEMPLATE
from app.processors.content_generator import content_generator
from app.storages import get_storage_provider
import logging

logger = logging.getLogger(__name__)

class SummaryService:
    def __init__(self):
        self.storage = get_storage_provider()
        self.content_generator = content_generator

    def get_document_summary(self, db: Session, document_id: str) -> DocumentSummary:
        return db.query(DocumentSummary).filter(DocumentSummary.document_id == document_id).first()

    def generate_document_summary(self, db: Session, document_id: str) -> DocumentSummary:
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                raise ValueError(f"Document with id {document_id} not found")

            existing_summary = self.get_document_summary(db, document_id)
            if existing_summary:
                logger.info(f"Summary already exists for document {document_id}")
                return existing_summary

            if not document.content_file_path:
                raise ValueError(f"Document content file not found: {document.content_file_path}")

            storage = get_storage_provider(document.storage_provider or "local")
            
            try:
                document_content = storage.read_file(document.content_file_path)
            except Exception as e:
                raise ValueError(f"Failed to read document content: {e}")

            if not document_content.strip():
                raise ValueError("Document content is empty")

            summary_prompt = SUMMARY_GENERATION_PROMPT_TEMPLATE.format(
                session_name=document.filename,
                document_count=1,
                content=document_content
            )
            
            logger.info(f"Generating summary for document {document_id}")
            summary_content = self.content_generator.generate_content(summary_prompt, "summary")
            
            if not summary_content:
                raise ValueError("Failed to generate summary content")

            summary_content = summary_content.replace('**', '')

            document_word_count = len(document_content.split())
            summary_word_count = len(summary_content.split())

            summary_file_path = storage.save_summary_file(content=summary_content,document_id=document.id)

            document_summary = DocumentSummary(
                document_id=document_id,
                summary_content=summary_content,
                document_count=1,
                total_word_count=document_word_count,
                summary_word_count=summary_word_count,
                summary_file_path=summary_file_path,
                generation_model=self.content_generator.model_name
            )

            db.add(document_summary)
            db.commit()
            db.refresh(document_summary)

            logger.info(f"Successfully generated summary for document {document_id}")
            return document_summary

        except Exception as e:
            logger.error(f"Error generating summary for document {document_id}: {str(e)}")
            db.rollback()
            raise

summary_service = SummaryService()
