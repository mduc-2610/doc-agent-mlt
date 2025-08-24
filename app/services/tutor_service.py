import uuid
import json
import traceback
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging

from app.models import (
    TutorSession, TutorInteraction, LearningProgress,
    Question, QuestionAnswer, Flashcard, Document
)
from app.schemas.tutor import (
    TutorSessionCreate, TutorInteractionCreate, TutorResponse,
    ExplainConceptRequest, FlashcardStudyRequest, FlashcardStudyResponse,
    QuestionPracticeRequest, QuestionPracticeResponse, UserQuestionRequest
)
from app.config import current_date_time
from app.processors.vector_processor import vector_processor
from app.processors.question_generator import question_generator
from app.utils.template import (
    TUTOR_EXPLANATION_PROMPT_TEMPLATE, TUTOR_ANSWER_PROMPT_TEMPLATE
)

logger = logging.getLogger(__name__)

class TutorService:
    def __init__(self):
        self.vector_processor = vector_processor
        self.question_generator = question_generator
    
    def create_tutor_session(self, db: Session, request: TutorSessionCreate) -> TutorSession:
        """Create a new tutor session"""
        try:
            tutor_session = TutorSession(
                session_id=request.session_id,
                user_id=request.user_id,
                tutor_type=request.tutor_type,
                current_context=request.current_context,
                progress_data={}
            )
            db.add(tutor_session)
            db.commit()
            db.refresh(tutor_session)
            
            # Initialize learning progress if doesn't exist
            self._init_learning_progress(db, request.user_id, request.session_id)
            
            return tutor_session
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create tutor session: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    def get_tutor_session(self, db: Session, session_id: str, user_id: str) -> Optional[TutorSession]:
        """Get active tutor session"""
        return (
            db.query(TutorSession)
            .options(joinedload(TutorSession.interactions))
            .filter(
                TutorSession.session_id == session_id,
                TutorSession.user_id == user_id,
                TutorSession.is_active == True
            )
            .first()
        )
    
    def explain_concept(self, db: Session, request: ExplainConceptRequest) -> TutorResponse:
        """Explain a concept using AI tutor"""
        try:
            # Get relevant context from documents
            document_ids = self._get_session_document_ids(db, request.session_id)
            
            if document_ids:
                context = self.vector_processor.get_relevant_context(
                    db, request.concept, document_ids, max_context_length=3000
                )
            else:
                context = ""
            
            # Generate explanation using AI
            explanation_prompt = self._build_explanation_prompt(
                request.concept, context, request.difficulty_level, request.learning_style
            )
            
            explanation = self.question_generator._generate_content(
                explanation_prompt, "explanation"
            )
            
            # Store interaction
            tutor_session = self.get_tutor_session(db, request.session_id, request.user_id)
            if not tutor_session:
                tutor_session = self.create_tutor_session(db, TutorSessionCreate(
                    session_id=request.session_id,
                    user_id=request.user_id,
                    tutor_type="explanation"
                ))
            
            self._store_interaction(
                db, tutor_session.id, "explanation", request.concept, 
                explanation, context
            )
            
            # Update learning progress
            self._update_learning_progress(db, request.user_id, request.session_id, 
                                         concepts_explained=1)
            
            return TutorResponse(
                response=explanation,
                confidence_score=0.85,
                context_used=context[:200] + "..." if len(context) > 200 else context,
                suggestions=self._generate_follow_up_suggestions(request.concept)
            )
            
        except Exception as e:
            logger.error(f"Failed to explain concept: {e}")
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    
    def handle_flashcard_study(self, db: Session, request: FlashcardStudyRequest) -> FlashcardStudyResponse:
        """Handle flashcard study session"""
        try:
            # Get flashcard to study
            if request.flashcard_id:
                flashcard = db.query(Flashcard).filter(Flashcard.id == request.flashcard_id).first()
            else:
                # Get next flashcard based on filters and progress
                flashcard = self._get_next_flashcard(db, request)
            
            if not flashcard:
                raise HTTPException(status_code=404, detail="No flashcards available for study")
            
            # Get learning progress
            progress = self._get_learning_progress(db, request.user_id, request.session_id)
            
            return FlashcardStudyResponse(
                flashcard_id=flashcard.id,
                question=flashcard.question,
                show_answer=False,
                progress_info={
                    "total_reviewed": progress.total_flashcards_reviewed if progress else 0,
                    "mastered": progress.flashcards_mastered if progress else 0,
                    "mastery_level": progress.mastery_level if progress else 0.0
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to handle flashcard study: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    def reveal_flashcard_answer(self, db: Session, flashcard_id: str, user_id: str, 
                               session_id: str, difficulty_rating: str) -> FlashcardStudyResponse:
        """Reveal flashcard answer and update progress"""
        try:
            flashcard = db.query(Flashcard).filter(Flashcard.id == flashcard_id).first()
            if not flashcard:
                raise HTTPException(status_code=404, detail="Flashcard not found")
            
            # Update learning progress
            mastered = difficulty_rating in ["easy", "good"]
            self._update_learning_progress(
                db, user_id, session_id,
                total_flashcards_reviewed=1,
                flashcards_mastered=1 if mastered else 0
            )
            
            # Store interaction
            tutor_session = self.get_tutor_session(db, session_id, user_id)
            if tutor_session:
                self._store_interaction(
                    db, tutor_session.id, "flashcard_review", 
                    f"Reviewed flashcard: {flashcard.question}", 
                    f"Answer: {flashcard.answer}", "",
                    related_flashcard_id=flashcard_id
                )
            
            progress = self._get_learning_progress(db, user_id, session_id)
            
            return FlashcardStudyResponse(
                flashcard_id=flashcard.id,
                question=flashcard.question,
                show_answer=True,
                answer=flashcard.answer,
                explanation=flashcard.explanation,
                progress_info={
                    "total_reviewed": progress.total_flashcards_reviewed if progress else 0,
                    "mastered": progress.flashcards_mastered if progress else 0,
                    "mastery_level": progress.mastery_level if progress else 0.0
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to reveal flashcard answer: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    def handle_question_practice(self, db: Session, request: QuestionPracticeRequest) -> QuestionPracticeResponse:
        """Handle question practice session"""
        try:
            # Get question to practice
            if request.question_id:
                question = (
                    db.query(Question)
                    .options(joinedload(Question.question_answers))
                    .filter(Question.id == request.question_id)
                    .first()
                )
            else:
                # Get next question based on filters
                question = self._get_next_question(db, request)
            
            if not question:
                raise HTTPException(status_code=404, detail="No questions available for practice")
            
            # Prepare options for multiple choice questions
            options = None
            if question.type in ["multiple_choice", "single_choice"]:
                options = [ans.content for ans in question.question_answers]
            
            progress = self._get_learning_progress(db, request.user_id, request.session_id)
            
            return QuestionPracticeResponse(
                question_id=question.id,
                question=question.content,
                question_type=question.type,
                options=options,
                progress_info={
                    "total_answered": progress.total_questions_answered if progress else 0,
                    "correct_answers": progress.correct_answers if progress else 0,
                    "accuracy": (progress.correct_answers / max(progress.total_questions_answered, 1)) if progress else 0.0
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to handle question practice: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    def submit_question_answer(self, db: Session, question_id: str, user_answer: str, 
                              user_id: str, session_id: str) -> QuestionPracticeResponse:
        """Submit answer to a practice question"""
        try:
            question = (
                db.query(Question)
                .options(joinedload(Question.question_answers))
                .filter(Question.id == question_id)
                .first()
            )
            
            if not question:
                raise HTTPException(status_code=404, detail="Question not found")
            
            # Check if answer is correct
            is_correct = self._check_answer_correctness(question, user_answer)
            
            # Update learning progress
            self._update_learning_progress(
                db, user_id, session_id,
                total_questions_answered=1,
                correct_answers=1 if is_correct else 0
            )
            
            # Store interaction
            tutor_session = self.get_tutor_session(db, session_id, user_id)
            if tutor_session:
                self._store_interaction(
                    db, tutor_session.id, "question_practice",
                    f"Answered: {user_answer}",
                    f"Correct: {is_correct}. Explanation: {question.explanation}",
                    "",
                    related_question_id=question_id
                )
            
            # Prepare options for response
            options = None
            if question.type in ["multiple_choice", "single_choice"]:
                options = [ans.content for ans in question.question_answers]
            
            progress = self._get_learning_progress(db, user_id, session_id)
            
            return QuestionPracticeResponse(
                question_id=question.id,
                question=question.content,
                question_type=question.type,
                options=options,
                user_answer=user_answer,
                is_correct=is_correct,
                explanation=question.explanation,
                progress_info={
                    "total_answered": progress.total_questions_answered if progress else 0,
                    "correct_answers": progress.correct_answers if progress else 0,
                    "accuracy": (progress.correct_answers / max(progress.total_questions_answered, 1)) if progress else 0.0
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to submit question answer: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    def answer_user_question(self, db: Session, request: UserQuestionRequest) -> TutorResponse:
        """Answer user's custom question using AI tutor"""
        try:
            # Get relevant context from documents
            document_ids = self._get_session_document_ids(db, request.session_id)
            
            context = ""
            if document_ids:
                context = self.vector_processor.get_relevant_context(
                    db, request.question, document_ids, max_context_length=3000
                )
            
            # Generate answer using AI
            answer_prompt = self._build_answer_prompt(request.question, context, request.context_hint)
            
            answer = self.question_generator._generate_content(answer_prompt, "answer")
            
            # Store interaction
            tutor_session = self.get_tutor_session(db, request.session_id, request.user_id)
            if not tutor_session:
                tutor_session = self.create_tutor_session(db, TutorSessionCreate(
                    session_id=request.session_id,
                    user_id=request.user_id,
                    tutor_type="learning"
                ))
            
            self._store_interaction(
                db, tutor_session.id, "question", request.question, 
                answer, context
            )
            
            return TutorResponse(
                response=answer,
                confidence_score=0.8,
                context_used=context[:200] + "..." if len(context) > 200 else context,
                suggestions=self._generate_related_suggestions(request.question),
                related_resources=self._get_related_resources(db, request.question, document_ids)
            )
            
        except Exception as e:
            logger.error(f"Failed to answer user question: {e}")
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    
    def get_learning_progress(self, db: Session, user_id: str, session_id: str) -> Optional[LearningProgress]:
        """Get learning progress for a user in a session"""
        return self._get_learning_progress(db, user_id, session_id)
    
    # Helper methods
    
    def _init_learning_progress(self, db: Session, user_id: str, session_id: str):
        """Initialize learning progress if it doesn't exist"""
        existing = self._get_learning_progress(db, user_id, session_id)
        if not existing:
            progress = LearningProgress(
                user_id=user_id,
                session_id=session_id,
                total_questions_answered=0,
                correct_answers=0,
                total_flashcards_reviewed=0,
                flashcards_mastered=0,
                concepts_explained=0,
                study_time_minutes=0,
                mastery_level=0.0
            )
            db.add(progress)
            db.commit()
    
    def _get_learning_progress(self, db: Session, user_id: str, session_id: str) -> Optional[LearningProgress]:
        """Get learning progress"""
        return (
            db.query(LearningProgress)
            .filter(
                LearningProgress.user_id == user_id,
                LearningProgress.session_id == session_id
            )
            .first()
        )
    
    def _update_learning_progress(self, db: Session, user_id: str, session_id: str, **updates):
        """Update learning progress"""
        try:
            progress = self._get_learning_progress(db, user_id, session_id)
            if progress:
                for key, value in updates.items():
                    if hasattr(progress, key):
                        current_value = getattr(progress, key)
                        setattr(progress, key, current_value + value)
                
                # Update mastery level
                if progress.total_questions_answered > 0:
                    accuracy = progress.correct_answers / progress.total_questions_answered
                    flashcard_mastery = (progress.flashcards_mastered / max(progress.total_flashcards_reviewed, 1))
                    progress.mastery_level = (accuracy * 0.6 + flashcard_mastery * 0.4)
                
                progress.last_activity = current_date_time()
                progress.updated_at = current_date_time()
                db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update learning progress: {e}")
    
    def _store_interaction(self, db: Session, tutor_session_id: uuid.UUID, interaction_type: str,
                          user_input: str, tutor_response: str, context_used: str,
                          related_question_id: str = None, related_flashcard_id: str = None):
        """Store tutor interaction"""
        try:
            interaction = TutorInteraction(
                tutor_session_id=tutor_session_id,
                interaction_type=interaction_type,
                user_input=user_input,
                tutor_response=tutor_response,
                context_used=context_used,
                related_question_id=related_question_id,
                related_flashcard_id=related_flashcard_id,
                confidence_score=0.8
            )
            db.add(interaction)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to store interaction: {e}")
    
    def _get_session_document_ids(self, db: Session, session_id: str) -> List[str]:
        """Get document IDs for a session"""
        documents = db.query(Document).filter(Document.session_id == session_id).all()
        return [str(doc.id) for doc in documents]
    
    def _get_next_flashcard(self, db: Session, request: FlashcardStudyRequest) -> Optional[Flashcard]:
        """Get next flashcard for study"""
        query = db.query(Flashcard).filter(Flashcard.session_id == request.session_id)
        
        if request.topic_filter:
            query = query.filter(Flashcard.topic.ilike(f"%{request.topic_filter}%"))
        
        return query.first()
    
    def _get_next_question(self, db: Session, request: QuestionPracticeRequest) -> Optional[Question]:
        """Get next question for practice"""
        query = (
            db.query(Question)
            .options(joinedload(Question.question_answers))
            .filter(Question.session_id == request.session_id)
        )
        
        if request.difficulty_filter:
            query = query.filter(Question.difficulty_level == request.difficulty_filter)
        
        if request.topic_filter:
            query = query.filter(Question.topic.ilike(f"%{request.topic_filter}%"))
        
        return query.first()
    
    def _check_answer_correctness(self, question: Question, user_answer: str) -> bool:
        """Check if user's answer is correct"""
        if question.type in ["multiple_choice", "single_choice"]:
            correct_answers = [ans for ans in question.question_answers if ans.is_correct]
            return any(ans.content.lower().strip() == user_answer.lower().strip() for ans in correct_answers)
        else:
            return question.correct_answer.lower().strip() in user_answer.lower().strip()
    
    def _build_explanation_prompt(self, concept: str, context: str, difficulty_level: str, learning_style: str) -> str:
        """Build prompt for concept explanation"""
        return TUTOR_EXPLANATION_PROMPT_TEMPLATE.format(
            concept=concept,
            context=context,
            difficulty_level=difficulty_level,
            learning_style=learning_style
        )
    
    def _build_answer_prompt(self, question: str, context: str, context_hint: str = None) -> str:
        """Build prompt for answering user questions"""
        context_hint_formatted = f"Additional context hint: {context_hint}" if context_hint else ""
        return TUTOR_ANSWER_PROMPT_TEMPLATE.format(
            question=question,
            context=context,
            context_hint=context_hint_formatted
        )
    
    def _generate_follow_up_suggestions(self, concept: str) -> List[str]:
        """Generate follow-up learning suggestions"""
        return [
            f"Practice questions related to {concept}",
            f"Explore related concepts to {concept}",
            f"Review flashcards on {concept}",
            f"Find more examples of {concept}"
        ]
    
    def _generate_related_suggestions(self, question: str) -> List[str]:
        """Generate related question suggestions"""
        return [
            "Ask for more details about this topic",
            "Request examples or case studies",
            "Ask about practical applications",
            "Explore related concepts"
        ]
    
    def _get_related_resources(self, db: Session, question: str, document_ids: List[str]) -> List[Dict[str, Any]]:
        """Get related resources (questions, flashcards, documents)"""
        resources = []
        
        # Get related questions
        related_questions = (
            db.query(Question)
            .filter(Question.content.ilike(f"%{question[:50]}%"))
            .limit(3)
            .all()
        )
        
        for q in related_questions:
            resources.append({
                "type": "question",
                "id": str(q.id),
                "title": q.content[:100] + "..." if len(q.content) > 100 else q.content,
                "topic": q.topic
            })
        
        # Get related flashcards
        related_flashcards = (
            db.query(Flashcard)
            .filter(Flashcard.question.ilike(f"%{question[:50]}%"))
            .limit(3)
            .all()
        )
        
        for f in related_flashcards:
            resources.append({
                "type": "flashcard",
                "id": str(f.id),
                "title": f.question[:100] + "..." if len(f.question) > 100 else f.question,
                "topic": f.topic
            })
        
        return resources

tutor_service = TutorService()
