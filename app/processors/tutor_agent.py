import json
import logging
import time
import hashlib
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from app.config import settings
from app.utils.error_handling import retry_on_exception, RetryableError
from openai import OpenAI

logger = logging.getLogger(__name__)

class TutorAgent:
    def __init__(self):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openai_api_key,
        )
        self.model_name = getattr(settings, "tutor_model_name", "deepseek/deepseek-r1-0528:free")
        self.max_retries = settings.rag.max_retries
        self.generation_timeout = settings.rag.generation_timeout
        self.cache: Dict[str, str] = {}

    def _hash(self, s: str) -> str:
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    @retry_on_exception(exceptions=(RetryableError, Exception), max_retries=3)
    def _complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 1500) -> str:
        try:
            key = self._hash(system_prompt + "\n" + user_prompt)
            if key in self.cache:
                return self.cache[key]

            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                extra_headers={
                    "HTTP-Referer": "https://openrouter.ai",
                    "X-Title": "RAG Tutor",
                },
                max_tokens=max_tokens,
                timeout=self.generation_timeout,
            )
            text = completion.choices[0].message.content
            if len(self.cache) < 1000:
                self.cache[key] = text
            return text
        except Exception as e:
            if "rate limit" in str(e).lower() or "timeout" in str(e).lower():
                raise RetryableError(f"Retryable API error: {e}")
            raise

    def clear_cache(self):
        n = len(self.cache)
        self.cache.clear()
        return n

tutor_agent = TutorAgent()