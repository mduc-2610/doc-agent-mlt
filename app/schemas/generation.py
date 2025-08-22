from pydantic import BaseModel
from typing import List, Dict, Any

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
    options: List[str] = []

class FlashcardValidator(BaseModel):
    type: str
    question: str
    answer: str
    explanation: str