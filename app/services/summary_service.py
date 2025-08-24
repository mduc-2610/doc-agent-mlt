from sqlalchemy.orm import Session
from app.models.document import Document, DocumentSummary
from app.utils.template import SUMMARY_GENERATION_PROMPT_TEMPLATE
from app.processors.question_generator import question_generator
import logging
import os

logger = logging.getLogger(__name__)

class SummaryService:
    def __init__(self):
        pass

    def get_document_summary(self, db: Session, document_id: str) -> DocumentSummary:
        """Get existing summary for a document"""
        return db.query(DocumentSummary).filter(DocumentSummary.document_id == document_id).first()

    def generate_document_summary(self, db: Session, document_id: str) -> DocumentSummary:
        """Generate a new summary for a document"""
        try:
            # Get the document
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                raise ValueError(f"Document with id {document_id} not found")

            # Check if summary already exists
            existing_summary = self.get_document_summary(db, document_id)
            if existing_summary:
                logger.info(f"Summary already exists for document {document_id}")
                return existing_summary

            # Read document content
            if not document.content_file_path or not os.path.exists(document.content_file_path):
                raise ValueError(f"Document content file not found: {document.content_file_path}")

            with open(document.content_file_path, 'r', encoding='utf-8') as file:
                document_content = file.read()

            if not document_content.strip():
                raise ValueError("Document content is empty")

            # Prepare prompt for summary generation
            summary_prompt = SUMMARY_GENERATION_PROMPT_TEMPLATE.format(
                session_name=document.filename,
                document_count=1,
                content=document_content
            )

            # Generate summary using the question generator's LLM
            logger.info(f"Generating summary for document {document_id}")
            summary_content = question_generator._generate_content(
                summary_prompt,
                content_type="summary"
            )

            if not summary_content:
                raise ValueError("Failed to generate summary content")

            # Calculate word counts
            document_word_count = len(document_content.split())
            summary_word_count = len(summary_content.split())

            # Create summary file path
            summary_filename = f"{document.id}_summary.txt"
            base_dir = os.path.dirname(document.content_file_path)
            summary_dir = os.path.join(base_dir, "..", "summary_files")
            summary_file_path = os.path.join(summary_dir, summary_filename)

            # Ensure directory exists
            os.makedirs(os.path.dirname(summary_file_path), exist_ok=True)

            # Save summary to file
            with open(summary_file_path, 'w', encoding='utf-8') as file:
                file.write(summary_content)

            # Create and save DocumentSummary record
            document_summary = DocumentSummary(
                document_id=document_id,
                summary_content=summary_content,
                document_count=1,
                total_word_count=document_word_count,
                summary_word_count=summary_word_count,
                summary_file_path=summary_file_path,
                generation_model=question_generator.model_name
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

    def get_or_generate_document_summary(self, db: Session, document_id: str) -> DocumentSummary:
        """Get existing summary or generate a new one"""
        existing_summary = self.get_document_summary(db, document_id)
        if existing_summary:
            return existing_summary
        
        return self.generate_document_summary(db, document_id)

summary_service = SummaryService()
