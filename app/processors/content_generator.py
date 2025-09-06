
import json
import hashlib
import logging
import re
import time
from typing import Dict, Any, Optional
from openai import OpenAI
from app.config import settings
from app.utils.helper import clean_json_response

logger = logging.getLogger(__name__)

class ContentGenerator:
    def __init__(self):
        self.client = OpenAI(
            base_url=settings.generation.base_url,
            api_key=settings.openai_api_key,
        )
        self.model_name = settings.generation.model_name
        self.cache = {}
    
    def _hash_content(self, content: str) -> str:
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def _validate_quiz_item(self, item: dict) -> bool:
        return (
            item.get("question") and 
            item.get("correct_answer") and 
            item.get("options") and 
            len(item.get("options", [])) >= 2
        )
    
    def _validate_flashcard_item(self, item: dict) -> bool:
        return item.get("question") and item.get("answer")
    
    def generate_content(self, prompt: str, content_type: str = "json") -> str:
        """Generate content with retry logic for rate limiting and failures"""
        max_retries = 3
        base_delay = 1.0
        
        for attempt in range(max_retries + 1):
            try:
                cache_key = self._hash_content(prompt)
                if cache_key in self.cache:
                    logger.debug("Using cached response")
                    return self.cache[cache_key]
                
                if content_type == "summary":
                    messages = [{"role": "user", "content": prompt}]
                else:
                    messages = [
                        {"role": "system", "content": "You are an expert content creator. Respond with valid JSON only."},
                        {"role": "user", "content": prompt}
                    ]
                
                completion = self.client.chat.completions.create(
                    extra_headers=settings.generation.headers,
                    model=self.model_name,
                    messages=messages,
                    max_tokens=3500,
                    temperature=0.2,
                    timeout=settings.rag.generation_timeout,
                    stream=False
                )
                
                response = completion.choices[0].message.content
                
                if response and len(response) > 50:
                    if len(self.cache) < 1000:  
                        self.cache[cache_key] = response
                
                return response
                
            except Exception as e:
                error_str = str(e)
                
                # Check if it's a rate limiting error
                if "429" in error_str or "rate" in error_str.lower():
                    if attempt < max_retries:
                        # Exponential backoff with jitter
                        delay = base_delay * (2 ** attempt) + (time.time() % 1)
                        logger.warning(f"Rate limited, retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries + 1})")
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(f"Rate limiting failed after {max_retries + 1} attempts: {e}")
                        return ""
                
                # For other errors, log and retry with shorter delay
                if attempt < max_retries:
                    delay = base_delay * 0.5
                    logger.warning(f"Content generation error, retrying in {delay}s: {e}")
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"Content generation failed after {max_retries + 1} attempts: {e}")
                    return ""
        
        return ""
    
    def generate_json_items(self, prompt: str, target_count: int, validator_func=None) -> list:
        try:
            response = self.generate_content(prompt, "json")
            if not response:
                return []
            
            items = clean_json_response(response)
            if not items:
                return []
            
            

            with open(f"content_generator_response.txt", "a", encoding="utf-8") as f:
                f.write(f"\n\n=== New Generation at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                f.write(f"\n\n---\nPrompt ---\n{prompt}\n")
                f.write(f"\n--- Response ---\n")
                f.write (f"{response}\n")
            

            if validator_func:
                items = [item for item in items if validator_func(item)]
            
            return items[:target_count]
            
        except Exception as e:
            logger.error(f"JSON generation failed: {e}")
            return []
    
    def _generate_content_chunked(self, prompt_template: str, topic: str, context: str, target_count: int, 
                                 chunk_size: int, validator_func, content_type: str) -> list:
        num_calls = (target_count + chunk_size - 1) // chunk_size
        all_items = []
        failed_calls = 0

        logger.info(f"Starting {content_type} generation: target={target_count}, chunk_size={chunk_size}, calls={num_calls}")
        
        for call_index in range(num_calls):
            remaining = target_count - len(all_items)
            current_chunk = min(chunk_size, remaining)
            if current_chunk <= 0:
                break
                
            prompt = prompt_template.format(
                topic=topic, context=context, target_count=current_chunk
            )

            items = self.generate_json_items(prompt, current_chunk, validator_func)
            
            if items:
                all_items.extend(items)
                logger.debug(f"Call {call_index + 1}: Generated {len(items)} valid {content_type}")
            else:
                failed_calls += 1
                logger.warning(f"Call {call_index + 1}: Failed to generate any valid {content_type}")
                
                if failed_calls >= 2 and len(all_items) < target_count * 0.5:
                    logger.info(f"Multiple failures detected, reducing chunk size for remaining calls")
                    chunk_size = max(1, chunk_size // 2)
            
            if len(all_items) >= target_count:
                break
        
        success_rate = (len(all_items) / target_count) * 100 if target_count > 0 else 0
        logger.info(f"Generated {len(all_items)}/{target_count} {content_type} ({success_rate:.1f}% success) using {num_calls} calls, {failed_calls} failed")
        return all_items[:target_count]
    
    def generate_questions_chunked(self, prompt_template: str, topic: str, context: str, target_count: int) -> list:
        return self._generate_content_chunked(
            prompt_template, topic, context, target_count,
            settings.generation.questions_per_chunk, self._validate_quiz_item, "questions"
        )
    
    def generate_flashcards_chunked(self, prompt_template: str, topic: str, context: str, target_count: int) -> list:
        return self._generate_content_chunked(
            prompt_template, topic, context, target_count,
            settings.generation.flashcards_per_chunk, self._validate_flashcard_item, "flashcards"
        )
    
    def clear_cache(self) -> int:
        cache_size = len(self.cache)
        self.cache.clear()
        logger.info(f"Cleared {cache_size} cached responses")
        return cache_size

content_generator = ContentGenerator()
