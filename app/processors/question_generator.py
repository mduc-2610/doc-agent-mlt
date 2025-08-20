# app/processors/question_generator.py
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
from app.models import Question, QuestionAnswer, Flashcard
from app.config import current_date_time
from app.utils.template import (
    RAG_FLASHCARD_PROMPT_TEMPLATE, 
    RAG_QUIZ_PROMPT_TEMPLATE,
    ANSWER_GENERATION_PROMPT_TEMPLATE,
    INCORRECT_ANSWER_PROMPT_TEMPLATE
)
from app.utils.helper import clean_json_response
from app.utils.error_handling import (
    retry_on_exception, 
    handle_llm_errors, 
    RetryableError, 
    ErrorCollector,
    safe_execute
)
from pydantic import BaseModel, ValidationError
import time
import hashlib

logger = logging.getLogger(__name__)

class QuestionAnswerData(BaseModel):
    content: str
    is_correct: bool
    explanation: str = ""

class QuestionData(BaseModel):
    question: str
    type: str
    difficulty_level: str
    correct_answer: str
    explanation: str
    topic: str
    source_context: str
    answers: List[QuestionAnswerData]

class FlashcardData(BaseModel):
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

class GenerationMetrics:
    """Track generation performance metrics"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.start_time = time.time()
        self.api_calls = 0
        self.successful_generations = 0
        self.failed_generations = 0
        self.retry_count = 0
        self.cache_hits = 0
        self.total_tokens_used = 0
    
    def record_api_call(self, success: bool = True, tokens: int = 0):
        self.api_calls += 1
        self.total_tokens_used += tokens
        if success:
            self.successful_generations += 1
        else:
            self.failed_generations += 1
    
    def record_retry(self):
        self.retry_count += 1
    
    def record_cache_hit(self):
        self.cache_hits += 1
    
    def get_summary(self) -> Dict[str, Any]:
        duration = time.time() - self.start_time
        return {
            "duration_seconds": duration,
            "api_calls": self.api_calls,
            "successful_generations": self.successful_generations,
            "failed_generations": self.failed_generations,
            "retry_count": self.retry_count,
            "cache_hits": self.cache_hits,
            "success_rate": self.successful_generations / max(self.api_calls, 1),
            "tokens_used": self.total_tokens_used,
            "avg_time_per_call": duration / max(self.api_calls, 1)
        }

class QuestionGenerator:
    def __init__(self):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openai_api_key,
        )
        self.model_name = "deepseek/deepseek-r1-0528:free"
        self.max_retries = settings.rag.max_retries
        self.generation_timeout = settings.rag.generation_timeout
        self.metrics = GenerationMetrics()
        self.content_cache = {}  
    
    def _hash_content(self, content: str) -> str:
        """Create hash for content caching"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    @retry_on_exception(
        exceptions=(RetryableError, Exception),
        max_retries=3
    )
    @handle_llm_errors
    def _make_api_call(self, prompt: str, max_tokens: int = 4000) -> str:
        """Make API call with enhanced error handling and retry logic"""
        try:
            cache_key = self._hash_content(prompt)
            if cache_key in self.content_cache:
                self.metrics.record_cache_hit()
                logger.debug("Retrieved response from cache")
                return self.content_cache[cache_key]
            
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
            
            # Cache successful response
            self.content_cache[cache_key] = response
            
            # Track metrics
            tokens_used = getattr(completion, 'usage', {}).get('total_tokens', 0)
            self.metrics.record_api_call(success=True, tokens=tokens_used)
            
            logger.debug(f"API call successful, response length: {len(response)}")
            return response
            
        except Exception as e:
            self.metrics.record_api_call(success=False)
            logger.error(f"API call failed: {e}")
            
            # Classify retryable vs non-retryable errors
            if "rate limit" in str(e).lower() or "timeout" in str(e).lower():
                raise RetryableError(f"Retryable API error: {e}")
            else:
                raise
    
    def _validate_and_retry(self, prompt: str, validator_class, target_count: int) -> List[Dict]:
        error_collector = ErrorCollector(max_errors=5)
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Generation attempt {attempt + 1}/{self.max_retries}")
                
                response = self._make_api_call(prompt)
                
                # Debug logging
                with open("debug_gen_response.txt", "a", encoding='utf-8') as f:
                    f.write("_" * 50 + "\n")
                    f.write(f"Attempt {attempt + 1} - Validator: {validator_class.__name__}\n")
                    f.write(f"Target count: {target_count}\n")
                    f.write(f"Response: {response[:500]}...\n")
                
                cleaned_response = clean_json_response(response)
                
                try:
                    parsed_data = json.loads(cleaned_response)
                except json.JSONDecodeError as e:
                    error_collector.add_error(
                        "json_parsing", 
                        e, 
                        {"response_preview": cleaned_response[:200]}
                    )
                    self.metrics.record_retry()
                    continue
                
                if not isinstance(parsed_data, list):
                    error_collector.add_error(
                        "data_format", 
                        ValueError("Response is not a list"), 
                        {"response_type": type(parsed_data).__name__}
                    )
                    self.metrics.record_retry()
                    continue
                
                # Validate individual items
                validated_items = []
                for i, item in enumerate(parsed_data):
                    validation_result = safe_execute(
                        f"validate_item_{i}",
                        lambda: validator_class(**item).dict(),
                        error_collector=error_collector,
                        context={"item_index": i, "item_preview": str(item)[:100]}
                    )
                    
                    if validation_result:
                        validated_items.append(validation_result)
                
                logger.info(f"Validated {len(validated_items)} items out of {len(parsed_data)}")
                
                # Check if we have enough valid items
                min_required = max(1, int(target_count * 0.6))  # At least 60% of target
                if len(validated_items) >= min_required:
                    logger.info(f"Generation successful: {len(validated_items)} valid items")
                    return validated_items[:target_count]
                
                logger.warning(f"Insufficient valid items: {len(validated_items)}/{min_required} required")
                self.metrics.record_retry()
                
                # If this is the last attempt, return what we have
                if attempt == self.max_retries - 1 and validated_items:
                    logger.warning("Returning partial results on final attempt")
                    return validated_items[:target_count]
                
            except RetryableError as e:
                self.metrics.record_retry()
                logger.warning(f"Retryable error on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(settings.rag.retry_delay_base * (2 ** attempt))
                continue
            
            except Exception as e:
                error_collector.add_error(f"attempt_{attempt + 1}", e)
                logger.error(f"Non-retryable error on attempt {attempt + 1}: {e}")
                break
        
        # If we get here, all attempts failed
        error_summary = error_collector.get_summary()
        logger.error(f"All generation attempts failed. Error summary: {error_summary}")
        
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to generate valid content after {self.max_retries} attempts. "
                   f"Total errors: {error_summary['total_errors']}"
        )
    
    def generate_rag_quiz(self, topic: str, context: str, target_count: int = 15) -> List[QuestionData]:
        """ quiz generation with better error handling"""
        try:
            self.metrics.reset()
            logger.info(f"Generating {target_count} quiz questions for topic: {topic}")
            
            # Validate inputs
            if not context.strip():
                raise ValueError("Context cannot be empty")
            
            if not topic.strip():
                raise ValueError("Topic cannot be empty")
            
            # Truncate context if too long
            max_context = 6000  # Leave room for prompt template
            if len(context) > max_context:
                context = context[:max_context] + "\n[Content truncated due to length]"
                logger.warning(f"Context truncated to {max_context} characters")
            
            quiz_prompt = RAG_QUIZ_PROMPT_TEMPLATE.format(
                topic=topic,
                context=context,
                target_count=target_count
            )
            
            logger.debug(f"Quiz prompt length: {len(quiz_prompt)}")
            
            validated_questions = self._validate_and_retry(
                quiz_prompt, QuestionValidator, target_count
            )
            
            # Convert to QuestionData objects
            quiz_objects = []
            for q in validated_questions:
                incorrect_answers = []
                if q.get("type") == "multiple_choice" and q.get("options"):
                    for opt in q.get("options", []):
                        is_correct = (opt == q.get("correct_answer"))
                        explanation = q.get("explanation", "") if is_correct else ""
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
            
            metrics_summary = self.metrics.get_summary()
            logger.info(f"Quiz generation completed. Metrics: {metrics_summary}")
            
            return quiz_objects
            
        except Exception as e:
            logger.error(f"Failed to generate RAG quiz: {e}")
            traceback.print_exc()
            return []
    
    def generate_rag_flashcards(self, topic: str, context: str, target_count: int = 15) -> List[FlashcardData]:
        """ flashcard generation with better error handling"""
        try:
            self.metrics.reset()
            logger.info(f"Generating {target_count} flashcards for topic: {topic}")
            
            # Validate inputs
            if not context.strip():
                raise ValueError("Context cannot be empty")
            
            if not topic.strip():
                raise ValueError("Topic cannot be empty")
            
            # Truncate context if too long
            max_context = 6000
            if len(context) > max_context:
                context = context[:max_context] + "\n[Content truncated due to length]"
                logger.warning(f"Context truncated to {max_context} characters")
            
            flashcard_prompt = RAG_FLASHCARD_PROMPT_TEMPLATE.format(
                topic=topic,
                context=context,
                target_count=target_count
            )
            
            logger.debug(f"Flashcard prompt length: {len(flashcard_prompt)}")
            
            validated_flashcards = self._validate_and_retry(
                flashcard_prompt, FlashcardValidator, target_count
            )
            
            # Convert to FlashcardData objects
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
            
            metrics_summary = self.metrics.get_summary()
            logger.info(f"Flashcard generation completed. Metrics: {metrics_summary}")
            
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
            
            if len(question) > 10:
                score += 0.2
            if len(answer) > 5:
                score += 0.2
            if len(explanation) > 10:
                score += 0.2
            
            context_words = set(context.lower().split())
            question_words = set(question.lower().split())
            answer_words = set(answer.lower().split())
            
            # Calculate overlap
            question_overlap = len(question_words.intersection(context_words)) / max(len(question_words), 1)
            answer_overlap = len(answer_words.intersection(context_words)) / max(len(answer_words), 1)
            
            context_relevance = (question_overlap + answer_overlap) / 2
            score += min(context_relevance * 0.4, 0.4)
            
            return min(score, 1.0)
            
        except Exception as e:
            logger.warning(f"Error calculating quality score: {e}")
            return 0.5  # Default neutral score
    
    def get_generation_stats(self) -> Dict[str, Any]:
        """Get comprehensive generation statistics"""
        return {
            "current_session": self.metrics.get_summary(),
            "cache_size": len(self.content_cache),
            "model_name": self.model_name,
            "configuration": {
                "max_retries": self.max_retries,
                "generation_timeout": self.generation_timeout,
                "retry_delay_base": settings.rag.retry_delay_base
            }
        }
    
    def clear_cache(self) -> int:
        """Clear content cache and return number of entries cleared"""
        cache_size = len(self.content_cache)
        self.content_cache.clear()
        logger.info(f"Cleared {cache_size} cached responses")
        return cache_size
    
    def optimize_prompt(self, base_prompt: str, context: str, target_count: int) -> str:
        """Optimize prompt based on context characteristics"""
        try:
            context_length = len(context)
            word_count = len(context.split())
            
            optimizations = []
            
            if context_length > 5000:
                optimizations.append("Focus on the most important concepts from this extensive content.")
            
            if word_count < 200:
                optimizations.append("Generate questions that make full use of all available information.")
            
            if any(keyword in context.lower() for keyword in ["process", "step", "procedure"]):
                optimizations.append("Include process-oriented questions about steps and sequences.")
            
            if any(keyword in context.lower() for keyword in ["definition", "term", "concept"]):
                optimizations.append("Include definition-based questions for key terms.")
            
            if any(keyword in context.lower() for keyword in ["example", "case", "instance"]):
                optimizations.append("Include application questions using the provided examples.")
            
            # Add optimizations to prompt
            if optimizations:
                optimization_text = "\n\nSPECIFIC INSTRUCTIONS:\n" + "\n".join(f"- {opt}" for opt in optimizations)
                base_prompt = base_prompt + optimization_text
            
            return base_prompt
            
        except Exception as e:
            logger.warning(f"Error optimizing prompt: {e}")
            return base_prompt

question_generator = QuestionGenerator()