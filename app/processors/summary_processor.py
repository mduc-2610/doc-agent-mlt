import os
import traceback
from typing import List
from openai import OpenAI
from app.config import settings
from app.utils.template import SUMMARY_GENERATION_PROMPT_TEMPLATE
import logging

logger = logging.getLogger(__name__)

class SummaryProcessor:
    def __init__(self):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openai_api_key,
        )
        self.model_name = "deepseek/deepseek-r1-0528:free"
        self.max_tokens = 4000

    def save_summary_to_file(self, summary_content: str, summary_id: str) -> str:
        """Save summary content to file and return file path"""
        os.makedirs(settings.summary_files_dir, exist_ok=True)
        file_path = os.path.join(settings.summary_files_dir, f"{summary_id}.txt")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(summary_content)
        return file_path

    def generate_session_summary(self, documents_content: List[str], session_name: str = "Session") -> str:
        try:
            combined_content = "\n\n".join(documents_content)
            
            max_content_length = 8000  
            if len(combined_content) > max_content_length:
                combined_content = combined_content[:max_content_length] + "...\n[Content truncated due to length]"
            
            prompt = SUMMARY_GENERATION_PROMPT_TEMPLATE.format(
                session_name=session_name,
                content=combined_content,
                document_count=len(documents_content)
            )
            
            completion = self.client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": "https://openrouter.ai/deepseek/deepseek-r1-0528:free",
                    "X-Title": "DeepSeek: R1 0528 (free)",
                },
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens
            )
            
            summary_content = completion.choices[0].message.content
            
            if not summary_content or summary_content.strip() == "":
                raise ValueError("Generated summary is empty")
            
            return summary_content.strip()
            
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            traceback.print_exc()
            raise

summary_processor = SummaryProcessor()