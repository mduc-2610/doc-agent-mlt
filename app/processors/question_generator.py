# app/processors/question_generator.py - Simplified question generator
import json
import re
from openai import OpenAI
from app.config import settings
import traceback
import logging
from dataclasses import dataclass
from typing import List, Dict, Any
from fastapi import HTTPException
from pydantic import BaseModel
from app.utils.template import RAG_FLASHCARD_PROMPT_TEMPLATE, RAG_QUIZ_PROMPT_TEMPLATE
from app.utils.helper import clean_json_response
from app.utils.error_handling import retry_on_exception, RetryableError
import time
import hashlib
from app.schemas.generation import (
    QuestionAnswerData,
    QuestionData,
    FlashcardData,
    QuestionValidator,
    FlashcardValidator
)

logger = logging.getLogger(__name__)

class QuestionGenerator:
    def __init__(self):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openai_api_key,
        )
        self.model_name = "deepseek/deepseek-r1-0528:free"
        self.max_retries = settings.rag.max_retries
        self.generation_timeout = settings.rag.generation_timeout
        self.cache = {}  
    
    def _hash_content(self, content: str) -> str:
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    @retry_on_exception(exceptions=(RetryableError, Exception), max_retries=3)
    def _make_api_call(self, prompt: str, max_tokens: int = 4000) -> str:
        try:
            cache_key = self._hash_content(prompt)
            if cache_key in self.cache:
                logger.debug("Retrieved response from cache")
                return self.cache[cache_key]
            
            logger.debug(f"Making API call with prompt length: {len(prompt)}")
            
            completion = self.client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": "https://openrouter.ai/deepseek/deepseek-r1-0528:free",
                    "X-Title": "DeepSeek: R1 0528 (free)",
                },
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                timeout=self.generation_timeout
            )
            
            response = completion.choices[0].message.content
            
            if len(self.cache) < 1000:  
                self.cache[cache_key] = response
            
            logger.debug(f"API call successful, response length: {len(response)}")
            return response
            
        except Exception as e:
            logger.error(f"API call failed: {e}")
            if "rate limit" in str(e).lower() or "timeout" in str(e).lower():
                raise RetryableError(f"Retryable API error: {e}")
            else:
                raise
    
    def _validate_and_parse(self, prompt: str, validator_class, target_count: int) -> List[Dict]:
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Generation attempt {attempt + 1}/{self.max_retries}")
                
                response = self._make_api_call(prompt)
                cleaned_response = clean_json_response(response)
                
                try:
                    parsed_data = json.loads(cleaned_response)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parsing failed: {e}")
                    if attempt < self.max_retries - 1:
                        time.sleep(1 * (2 ** attempt))  
                        continue
                    else:
                        raise
                
                if not isinstance(parsed_data, list):
                    logger.warning("Response is not a list")
                    if attempt < self.max_retries - 1:
                        continue
                    else:
                        raise ValueError("Response is not a list")
                
                validated_items = []
                for item in parsed_data:
                    try:
                        validated_item = validator_class(**item).dict()
                        validated_items.append(validated_item)
                    except Exception as e:
                        logger.warning(f"Item validation failed: {e}")
                        continue
                
                min_required = max(1, int(target_count * 0.6)) 
                if len(validated_items) >= min_required:
                    logger.info(f"Generation successful: {len(validated_items)} valid items")
                    return validated_items[:target_count]
                
                logger.warning(f"Insufficient valid items: {len(validated_items)}/{min_required} required")
                
                if attempt == self.max_retries - 1 and validated_items:
                    logger.warning("Returning partial results on final attempt")
                    return validated_items[:target_count]
                
                time.sleep(1 * (2 ** attempt))
                
            except RetryableError as e:
                logger.warning(f"Retryable error on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(1 * (2 ** attempt))
                continue
            
            except Exception as e:
                logger.error(f"Non-retryable error on attempt {attempt + 1}: {e}")
                break
        
        logger.error("All generation attempts failed")
        raise HTTPException(status_code=500, detail=f"Failed to generate content after {self.max_retries} attempts")
    
    def generate_rag_quiz(self, topic: str, context: str, target_count: int = 15) -> List[QuestionData]:
        try:
            logger.info(f"Generating {target_count} quiz questions for topic: {topic}")
            
            if not context.strip():
                raise ValueError("Context cannot be empty")
            if not topic.strip():
                raise ValueError("Topic cannot be empty")
            
            max_context = 6000
            if len(context) > max_context:
                context = context[:max_context] + "\n[Content truncated]"
                logger.warning(f"Context truncated to {max_context} characters")
            
            quiz_prompt = RAG_QUIZ_PROMPT_TEMPLATE.format(
                topic=topic,
                context=context,
                target_count=target_count
            )
            
            validated_questions = self._validate_and_parse(
                quiz_prompt, QuestionValidator, target_count
            )
            
            quiz_objects = []
            for q in validated_questions:
                answers = []
                if q.get("type") == "multiple_choice" and q.get("options"):
                    for opt in q.get("options", []):
                        is_correct = (opt == q.get("correct_answer"))
                        answers.append(QuestionAnswerData(
                            content=opt,
                            is_correct=is_correct,
                            explanation=q.get("explanation", "") if is_correct else ""
                        ))
                
                quiz_objects.append(QuestionData(
                    question=q.get("question", ""),
                    type=q.get("type", "multiple_choice"),
                    difficulty_level=q.get("difficulty_level", "medium"),
                    correct_answer=q.get("correct_answer", ""),
                    explanation=q.get("explanation", ""),
                    topic=topic,
                    source_context=context[:500],
                    answers=answers
                ))
            
            logger.info(f"Quiz generation completed: {len(quiz_objects)} questions")
            return quiz_objects
            
        except Exception as e:
            logger.error(f"Failed to generate RAG quiz: {e}")
            traceback.print_exc()
            return []
    
    def generate_rag_flashcards(self, topic: str, context: str, target_count: int = 15) -> List[FlashcardData]:
        try:
            logger.info(f"Generating {target_count} flashcards for topic: {topic}")
            
            if not context.strip():
                raise ValueError("Context cannot be empty")
            if not topic.strip():
                raise ValueError("Topic cannot be empty")
            
            max_context = 6000
            if len(context) > max_context:
                context = context[:max_context] + "\n[Content truncated]"
                logger.warning(f"Context truncated to {max_context} characters")
            
            flashcard_prompt = RAG_FLASHCARD_PROMPT_TEMPLATE.format(
                topic=topic,
                context=context,
                target_count=target_count
            )
            
            validated_flashcards = self._validate_and_parse(
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
            
            logger.info(f"Flashcard generation completed: {len(flashcard_objects)} flashcards")
            return flashcard_objects

        except Exception as e:
            logger.error(f"Failed to generate RAG flashcards: {e}")
            traceback.print_exc()
            return []
    
    def calculate_quality_score(self, content: Dict[str, Any], context: str) -> float:
        try:
            question = content.get("question", "")
            answer = content.get("answer", content.get("correct_answer", ""))
            explanation = content.get("explanation", "")
            
            score = 0.0
            
            # Basic length checks
            if len(question) > 10:
                score += 0.3
            if len(answer) > 5:
                score += 0.3
            if len(explanation) > 10:
                score += 0.4
            
            return min(score, 1.0)
            
        except Exception as e:
            logger.warning(f"Error calculating quality score: {e}")
            return 0.5
    def clear_cache(self) -> int:
        """Clear response cache"""
        cache_size = len(self.cache)
        self.cache.clear()
        logger.info(f"Cleared {cache_size} cached responses")
        return cache_size

question_generator = QuestionGenerator()