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
from app.config import current_date_time
from app.utils.template import (
    RAG_FLASHCARD_PROMPT_TEMPLATE, 
    RAG_QUIZ_PROMPT_TEMPLATE,
    ANSWER_GENERATION_PROMPT_TEMPLATE,
    INCORRECT_ANSWER_PROMPT_TEMPLATE
)
from app.utils.helper import clean_json_response
from pydantic import BaseModel, ValidationError
import time

logger = logging.getLogger(__name__)

@dataclass
class QuestionAnswerData:
    content: str
    is_correct: bool
    explanation: str = ""

@dataclass
class QuestionData:
    question: str
    type: str
    difficulty_level: str
    correct_answer: str
    explanation: str
    topic: str
    source_context: str
    answers: List[QuestionAnswerData]

@dataclass
class FlashcardData:
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

class QuestionGenerator:
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
                
                validated_items = []
                for item in parsed_data:
                    try:
                        validated_item = validator_class(**item)
                        validated_items.append(validated_item.dict())
                    except ValidationError as e:
                        logger.warning(f"Validation failed for item: {e}")
                        continue
                
                if len(validated_items) >= target_count * 0.8:
                    return validated_items[:target_count]
                
                logger.warning(f"Attempt {attempt + 1}: Only got {len(validated_items)} valid items, retrying...")
                
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {e}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(1)
        
        raise HTTPException(status_code=500, detail="Failed to generate valid content after retries")
    
    def generate_rag_quiz(self, topic: str, context: str, target_count: int = 15) -> List[QuestionData]:
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
                incorrect_answers = []
                if q.get("type") == "multiple_choice" and q.get("options"):
                    for opt in q.get("options", []):
                        is_correct = (opt == q.get("correct_answer"))
                        explanation = q.get("explanation", "")
                        incorrect_answers.append(QuestionAnswerData(
                            content=opt,
                            is_correct=is_correct,
                            explanation=explanation
                        ))
                
                quiz_objects.append(QuestionData(
                    question=q.get("question", ""),
                    type=q.get("type", "multiple_choice"),
                    difficulty_level=q.get("difficulty_level", "medium"),
                    correct_answer=q.get("correct_answer", ""),
                    explanation=q.get("explanation", ""),
                    topic=topic,
                    source_context=context[:500],
                    answers=incorrect_answers
                ))
            
            return quiz_objects
            
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Failed to generate RAG quiz: {e}")
            return []
    
    def generate_rag_flashcards(self, topic: str, context: str, target_count: int = 15) -> List[FlashcardData]:
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
                FlashcardData(
                    card_type=f.get("type", "concept_flashcard"),
                    question=f.get("question", ""),
                    answer=f.get("answer", ""),
                    explanation=f.get("explanation", ""),
                    topic=topic,
                    source_context=context[:500]
                )
                for f in validated_flashcards
            ]
            return flashcard_objects

        except Exception as e:
            traceback.print_exc()
            logger.error(f"Failed to generate RAG flashcards: {e}")
            return []
    
    def calculate_quality_score(self, content: Dict[str, Any], context: str) -> float:
        """Calculate a quality score for generated content"""
        score = 0.0
        
        if len(content.get('question', '')) > 20:
            score += 0.3
        if len(content.get('answer', '')) > 10:
            score += 0.3
        if len(content.get('explanation', '')) > 20:
            score += 0.2
        
        question_text = content.get('question', '').lower()
        context_lower = context.lower()
        common_words = set(question_text.split()) & set(context_lower.split())
        if len(common_words) > 2:
            score += 0.2
        
        return min(score, 1.0)

question_generator = QuestionGenerator()