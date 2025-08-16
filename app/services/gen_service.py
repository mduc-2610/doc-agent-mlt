import json
import re
from openai import OpenAI
from app.config import settings
import traceback
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import uuid
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, UploadFile
from app.models import Question, QuestionAnswer, Flashcard, QuestionGeneration
from app.services import document_service, summarize_service
from app.services.vector_service import vector_service
import traceback
import logging
from app.config import current_date_time
from app.utils.template import (
    RAG_FLASHCARD_PROMPT_TEMPLATE, 
    RAG_QUIZ_PROMPT_TEMPLATE,
    ANSWER_GENERATION_PROMPT_TEMPLATE,
    INCORRECT_ANSWER_PROMPT_TEMPLATE
)
from app.utils.helper import clean_json_response, detect_file_type, detect_url_type
from pydantic import BaseModel, ValidationError
import time

logger = logging.getLogger(__name__)

@dataclass
class QuizAnswer:
    content: str
    is_correct: bool
    explanation: str = ""

@dataclass
class QuizQuestion:
    question: str
    type: str
    difficulty_level: str
    correct_answer: str
    explanation: str
    topic: str
    source_context: str
    answers: List[QuizAnswer]

@dataclass
class FlashcardItem:
    card_type: str
    question: str
    answer: str
    explanation: str
    topic: str
    source_context: str

class QuestionValidator(BaseModel):
    question: str
    type: str
    difficulty_level: str
    correct_answer: str
    explanation: str
    options: Optional[List[str]] = None

class FlashcardValidator(BaseModel):
    type: str
    question: str
    answer: str
    explanation: str

class EnhancedQuizGenerationService:
    def __init__(self):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openai_api_key,
        )
        self.model_name = "deepseek/deepseek-r1-0528:free"
        self.max_retries = 3
    
    def _make_api_call(self, prompt: str, max_tokens: int = 2000) -> str:
        """Make API call with error handling"""
        try:
            completion = self.client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": "https://openrouter.ai/deepseek/deepseek-r1-0528:free",
                    "X-Title": "DeepSeek: R1 0528 (free)",
                },
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens
            )
            return completion.choices[0].message.content
        except Exception as e:
            logger.error(f"API call failed: {e}")
            raise
    
    def _validate_and_retry(self, prompt: str, validator_class, target_count: int) -> List[Dict]:
        """Generate content with validation and retry logic"""
        for attempt in range(self.max_retries):
            try:
                response = self._make_api_call(prompt)
                cleaned_response = clean_json_response(response)
                parsed_data = json.loads(cleaned_response)
                
                # Validate each item
                validated_items = []
                for item in parsed_data:
                    try:
                        validated_item = validator_class(**item)
                        validated_items.append(validated_item.dict())
                    except ValidationError as e:
                        logger.warning(f"Validation failed for item: {e}")
                        continue
                
                if len(validated_items) >= target_count * 0.8:  # Accept if we get 80% of target
                    return validated_items[:target_count]
                
                logger.warning(f"Attempt {attempt + 1}: Only got {len(validated_items)} valid items, retrying...")
                
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {e}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(1)  # Brief delay before retry
        
        raise HTTPException(status_code=500, detail="Failed to generate valid content after retries")
    
    def generate_rag_quiz(self, topic: str, context: str, target_count: int = 15) -> List[QuizQuestion]:
        """Generate quiz questions using RAG approach"""
        quiz_prompt = RAG_QUIZ_PROMPT_TEMPLATE.format(
            topic=topic,
            context=context,
            target_count=target_count
        )
        
        try:
            validated_questions = self._validate_and_retry(
                quiz_prompt, QuestionValidator, target_count
            )
            
            quiz_objects = []
            for q in validated_questions:
                # Generate incorrect answers for multiple choice questions
                incorrect_answers = []
                if q.get("type") == "multiple_choice" and q.get("options"):
                    for opt in q.get("options", []):
                        is_correct = (opt == q.get("correct_answer"))
                        explanation = q.get("explanation", "") if is_correct else self._generate_incorrect_explanation(opt, q.get("correct_answer"), context)
                        incorrect_answers.append(QuizAnswer(
                            content=opt,
                            is_correct=is_correct,
                            explanation=explanation
                        ))
                
                quiz_objects.append(QuizQuestion(
                    question=q.get("question", ""),
                    type=q.get("type", "multiple_choice"),
                    difficulty_level=q.get("difficulty_level", "medium"),
                    correct_answer=q.get("correct_answer", ""),
                    explanation=q.get("explanation", ""),
                    topic=topic,
                    source_context=context[:500],  # Store first 500 chars of context
                    answers=incorrect_answers
                ))
            
            return quiz_objects
            
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Failed to generate RAG quiz: {e}")
            return []
    
    def generate_rag_flashcards(self, topic: str, context: str, target_count: int = 15) -> List[FlashcardItem]:
        """Generate flashcards using RAG approach"""
        flashcard_prompt = RAG_FLASHCARD_PROMPT_TEMPLATE.format(
            topic=topic,
            context=context,
            target_count=target_count
        )
        
        try:
            validated_flashcards = self._validate_and_retry(
                flashcard_prompt, FlashcardValidator, target_count
            )
            
            flashcard_objects = [
                FlashcardItem(
                    card_type=f.get("type", "concept_flashcard"),
                    question=f.get("question", ""),
                    answer=f.get("answer", ""),
                    explanation=f.get("explanation", ""),
                    topic=topic,
                    source_context=context[:500]  # Store first 500 chars of context
                )
                for f in validated_flashcards
            ]
            return flashcard_objects

        except Exception as e:
            traceback.print_exc()
            logger.error(f"Failed to generate RAG flashcards: {e}")
            return []
    
    def _generate_incorrect_explanation(self, incorrect_answer: str, correct_answer: str, context: str) -> str:
        """Generate explanation for why an answer is incorrect"""
        prompt = INCORRECT_ANSWER_PROMPT_TEMPLATE.format(
            incorrect_answer=incorrect_answer,
            correct_answer=correct_answer,
            context=context[:1000]
        )
        
        try:
            response = self._make_api_call(prompt, max_tokens=200)
            return response.strip()
        except Exception as e:
            logger.error(f"Failed to generate incorrect answer explanation: {e}")
            return f"This answer is incorrect. The correct answer is: {correct_answer}"
    
    def calculate_quality_score(self, content: Dict[str, Any], context: str) -> float:
        """Calculate a quality score for generated content"""
        score = 0.0
        
        # Check if question/answer are substantial
        if len(content.get('question', '')) > 20:
            score += 0.3
        if len(content.get('answer', '')) > 10:
            score += 0.3
        if len(content.get('explanation', '')) > 20:
            score += 0.2
        
        # Check if content relates to context (simple keyword matching)
        question_text = content.get('question', '').lower()
        context_lower = context.lower()
        common_words = set(question_text.split()) & set(context_lower.split())
        if len(common_words) > 2:
            score += 0.2
        
        return min(score, 1.0)

# Enhanced generation service
enhanced_ai_generator = EnhancedQuizGenerationService()

def process_rag_quiz_and_flashcards(
    topic: str,
    document_ids: List[str],
    session_id: str,
    user_id: str,
    quiz_count: int,
    flashcard_count: int,
    db: Session,
) -> Dict[str, Any]:
    """Process quiz and flashcard generation using RAG approach"""
    try:
        # Get relevant context using vector search
        relevant_context = vector_service.get_relevant_context(
            db, topic, document_ids, max_context_length=4000
        )
        
        if not relevant_context.strip():
            raise HTTPException(status_code=400, detail="No relevant context found for the given topic")
        
        # Create generation record for tracking
        generation_record = QuestionGeneration(
            user_input=f"Topic: {topic}",
            context_chunks=[{"content": relevant_context, "source": "vector_search"}],
            generation_parameters={
                "quiz_count": quiz_count,
                "flashcard_count": flashcard_count,
                "model": enhanced_ai_generator.model_name,
                "document_ids": document_ids
            },
            model_version=enhanced_ai_generator.model_name,
            generation_status="processing"
        )
        db.add(generation_record)
        db.flush()
        
        # Generate content
        quiz_questions = enhanced_ai_generator.generate_rag_quiz(topic, relevant_context, quiz_count)
        flashcards = enhanced_ai_generator.generate_rag_flashcards(topic, relevant_context, flashcard_count)
        
        # Store questions in database
        for q in quiz_questions:
            quality_score = enhanced_ai_generator.calculate_quality_score(
                {"question": q.question, "answer": q.correct_answer, "explanation": q.explanation},
                relevant_context
            )
            
            question_obj = Question(
                content=q.question,
                type=q.type,
                difficulty_level=q.difficulty_level,
                topic=q.topic,
                correct_answer=q.correct_answer,
                document_id=document_ids[0] if document_ids else None,  # Associate with first document
                session_id=session_id,
                user_id=user_id,
                explanation=q.explanation,
                source_context=q.source_context,
                generation_model=enhanced_ai_generator.model_name,
                validation_score=quality_score,
                created_at=current_date_time()
            )
            db.add(question_obj)
            db.flush()

            for ans in q.answers:
                answer_obj = QuestionAnswer(
                    content=ans.content,
                    is_correct=ans.is_correct,
                    explanation=ans.explanation,
                    question_id=question_obj.id
                )
                db.add(answer_obj)

        # Store flashcards in database
        for f in flashcards:
            quality_score = enhanced_ai_generator.calculate_quality_score(
                {"question": f.question, "answer": f.answer, "explanation": f.explanation},
                relevant_context
            )
            
            flashcard_obj = Flashcard(
                card_type=f.card_type,
                question=f.question,
                answer=f.answer,
                explanation=f.explanation,
                topic=f.topic,
                source_context=f.source_context,
                generation_model=enhanced_ai_generator.model_name,
                validation_score=quality_score,
                document_id=document_ids[0] if document_ids else None,
                session_id=session_id,
                user_id=user_id,
                created_at=current_date_time()
            )
            db.add(flashcard_obj)

        # Update generation record
        generation_record.output_questions = [
            {"type": "quiz", "count": len(quiz_questions)},
            {"type": "flashcard", "count": len(flashcards)}
        ]
        generation_record.final_questions = generation_record.output_questions
        generation_record.generation_status = "completed"
        generation_record.updated_at = current_date_time()

        db.commit()

        return {
            "generation_id": str(generation_record.id),
            "topic": topic,
            "document_ids": document_ids,
            "session_id": session_id,
            "quiz_questions": quiz_questions,
            "flashcards": flashcards,
            "context_used": relevant_context[:200] + "..." if len(relevant_context) > 200 else relevant_context,
            "created_at": current_date_time()
        }

    except Exception as e:
        db.rollback()
        if 'generation_record' in locals():
            generation_record.generation_status = "failed"
            generation_record.updated_at = current_date_time()
            db.commit()
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# Keep original functions for backward compatibility
def generate_quiz_from_url_service(
    url: str,
    user_id: str,
    session_id: str,
    quiz_count: int,
    flashcard_count: int,
    target_chunks: int,
    db: Session,
):
    """Original URL-based generation (enhanced with embeddings)"""
    try:
        url_type = detect_url_type(url)

        if url_type == "youtube":
            document = document_service.parse_youtube(db, url, session_id)
        else:
            document = document_service.parse_web_url(db, url, session_id)

        document_id = str(document.id)
        
        # Create embeddings for the document
        with open(document.content_file_path, 'r', encoding='utf-8') as f:
            text_content = f.read()
        
        vector_service.chunk_and_embed_document(db, document_id, text_content, target_chunks)
        
        # Use RAG-based generation with the document
        return process_rag_quiz_and_flashcards(
            topic="General content analysis",  # Default topic
            document_ids=[document_id],
            session_id=str(document.session_id) if document.session_id else None,
            user_id=user_id,
            quiz_count=quiz_count,
            flashcard_count=flashcard_count,
            db=db,
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

def generate_quiz_from_file_service(
    file: UploadFile,
    user_id: str,
    session_id: str,
    quiz_count: int,
    flashcard_count: int,
    target_chunks: int,
    db: Session,
):
    """Original file-based generation (enhanced with embeddings)"""
    try:
        file_type = detect_file_type(file)

        if file_type == "audio_video":
            document = document_service.parse_audio_video(db, file, session_id)
        else:
            document = document_service.parse_document(db, file, session_id)

        document_id = str(document.id)
        
        # Create embeddings for the document
        with open(document.content_file_path, 'r', encoding='utf-8') as f:
            text_content = f.read()
        
        vector_service.chunk_and_embed_document(db, document_id, text_content, target_chunks)
        
        # Use RAG-based generation with the document
        return process_rag_quiz_and_flashcards(
            topic="General content analysis",  # Default topic
            document_ids=[document_id],
            session_id=str(document.session_id) if document.session_id else None,
            user_id=user_id,
            quiz_count=quiz_count,
            flashcard_count=flashcard_count,
            db=db,
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))