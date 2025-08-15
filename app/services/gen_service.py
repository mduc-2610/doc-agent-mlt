import json
import re
from openai import OpenAI
from app.config import settings
import traceback
import logging
from dataclasses import dataclass
from typing import List
import uuid
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, UploadFile
from app.models import Question, QuestionAnswer, Flashcard
from app.services import document_service, summarize_service
import traceback
import logging
from app.config import current_date_time
from app.utils.template import FLASHCARD_PROMPT_TEMPLATE, QUIZ_PROMPT_TEMPLATE
from app.utils.helper import clean_json_response, detect_file_type, detect_url_type

logger = logging.getLogger(__name__)


@dataclass
class QuizAnswer:
    content: str
    is_correct: bool

@dataclass
class QuizQuestion:
    question: str
    type: str
    difficulty_level: str
    correct_answer: str
    explanation: str
    answers: List[QuizAnswer]

@dataclass
class FlashcardItem:
    card_type: str
    question: str
    answer: str
    explanation: str

logger = logging.getLogger(__name__)

class QuizGenerationService:
    def __init__(self):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openai_api_key,
        )
    
    def generate_quiz(self, text: str, target_count: int = 15):
        quiz_prompt = QUIZ_PROMPT_TEMPLATE.format(text=text, target_count=target_count)
        
        try:
            completion = self.client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": "https://openrouter.ai/deepseek/deepseek-r1-0528:free",
                    "X-Title": "DeepSeek: R1 0528 (free)",
                },
                model="deepseek/deepseek-r1-0528:free",
                messages=[{"role": "user", "content": quiz_prompt}]
            )
            
            response_text = clean_json_response(completion.choices[0].message.content)
            quiz_list = json.loads(response_text)

            quiz_objects = []
            for q in quiz_list:
                answers = []
                if q.get("type") == "multiple_choice":
                    for opt in q.get("options", []):
                        answers.append(QuizAnswer(
                            content=opt,
                            is_correct=(opt == q.get("correct_answer"))
                        ))
                quiz_objects.append(QuizQuestion(
                    question=q.get("question", ""),
                    type=q.get("type", "multiple_choice"),
                    difficulty_level=q.get("difficulty", "medium"),
                    correct_answer=q.get("correct_answer", ""),
                    explanation=q.get("explanation", ""),
                    answers=answers
                ))
            return quiz_objects
            
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Failed to generate quiz: {e}")
            return []
    
    def generate_flashcards(self, text: str, target_count: int = 15):
        flashcard_prompt = FLASHCARD_PROMPT_TEMPLATE.format(text=text, target_count=target_count)
        
        try:
            completion = self.client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": "https://openrouter.ai/deepseek/deepseek-r1-0528:free",
                    "X-Title": "DeepSeek: R1 0528 (free)",
                },
                model="deepseek/deepseek-r1-0528:free",
                messages=[{"role": "user", "content": flashcard_prompt}]
            )
            
            response_text = clean_json_response(completion.choices[0].message.content)
            flashcard_list = json.loads(response_text)

            flashcard_objects = [
                FlashcardItem(
                    card_type=f.get("type", "concept_flashcard"),
                    question=f.get("question", ""),
                    answer=f.get("answer", ""),
                    explanation=f.get("explanation", "")
                )
                for f in flashcard_list
            ]
            return flashcard_objects

        except Exception as e:
            traceback.print_exc()
            logger.error(f"Failed to generate flashcards: {e}")
            return []

ai_generator = QuizGenerationService()

def process_quiz_and_flashcards(
    document_id: str,
    session_id: str,
    user_id: str,
    global_summary: str,
    quiz_count: int,
    flashcard_count: int,
    db: Session,
):
    try:
        quiz_questions = ai_generator.generate_quiz(global_summary, quiz_count)
        flashcards = ai_generator.generate_flashcards(global_summary, flashcard_count)

        for q in quiz_questions:
            question_obj = Question(
                content=q.question,
                type=q.type,
                difficulty_level=q.difficulty_level,
                correct_answer=q.correct_answer,
                document_id=document_id,
                session_id=session_id,
                user_id=user_id,
                explanation=q.explanation,
                created_at=current_date_time()
            )
            db.add(question_obj)
            db.flush()

            for ans in q.answers:
                answer_obj = QuestionAnswer(
                    content=ans.content,
                    is_correct=ans.is_correct,
                    question_id=question_obj.id
                )
                db.add(answer_obj)

        for f in flashcards:
            flashcard_obj = Flashcard(
                card_type=f.card_type,
                question=f.question,
                answer=f.answer,
                explanation=f.explanation,
                document_id=document_id,
                session_id=session_id,
                user_id=user_id,
                created_at=current_date_time()
            )
            db.add(flashcard_obj)

        db.commit()

        return {
            "document_id": document_id,
            "session_id": session_id,
            "quiz_questions": quiz_questions,
            "flashcards": flashcards,
            "created_at": current_date_time()
        }

    except Exception as e:
        db.rollback()
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

def generate_quiz_from_url_service(
    url: str,
    user_id: str,
    session_id: str,
    quiz_count: int,
    flashcard_count: int,
    target_chunks: int,
    db: Session,
):
    try:
        url_type = detect_url_type(url)

        if url_type == "youtube":
            document = document_service.parse_youtube(db, url, session_id)
        else:
            document = document_service.parse_web_url(db, url, session_id)

        document_id = str(document.id)
        session_id = str(document.session_id) if document.session_id else None

        summary = summarize_service.create_summary(db, document_id, target_chunks)
        global_summary = summary.global_summary

        return process_quiz_and_flashcards(
            document_id=document_id,
            session_id=session_id,
            user_id=user_id,
            global_summary=global_summary,
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
    try:
        file_type = detect_file_type(file)

        if file_type == "audio_video":
            document = document_service.parse_audio_video(db, file, session_id)
        else:
            document = document_service.parse_document(db, file, session_id)

        document_id = str(document.id)
        session_id = str(document.session_id) if document.session_id else None

        summary = summarize_service.create_summary(db, document_id, target_chunks)
        global_summary = summary.global_summary

        return process_quiz_and_flashcards(
            document_id=document_id,
            session_id=session_id,
            user_id=user_id,
            global_summary=global_summary,
            quiz_count=quiz_count,
            flashcard_count=flashcard_count,
            db=db,
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))