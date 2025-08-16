from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from app.database import get_db
from app.services import quiz_service, gen_service
from app.services.vector_service import vector_service
from app.models import QuestionGeneration
import traceback

router = APIRouter()

class TopicGenerationRequest(BaseModel):
    topic: str
    document_ids: List[str]
    session_id: Optional[str] = None
    user_id: str
    quiz_count: int = 15
    flashcard_count: int = 15

class ReviewRequest(BaseModel):
    generation_id: str
    action: str  # "approve", "reject", "approve_selected"
    selected_question_ids: Optional[List[str]] = None
    reviewer_notes: Optional[str] = None

@router.post("/generate/topic")
async def generate_quiz_from_topic(
    request: TopicGenerationRequest,
    db: Session = Depends(get_db)
):
    """Generate quiz and flashcards based on a topic using RAG"""
    try:
        return gen_service.process_rag_quiz_and_flashcards(
            topic=request.topic,
            document_ids=request.document_ids,
            session_id=request.session_id,
            user_id=request.user_id,
            quiz_count=request.quiz_count,
            flashcard_count=request.flashcard_count,
            db=db
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search-context/{topic}")
async def search_relevant_context(
    topic: str,
    document_ids: Optional[str] = None,  # Comma-separated document IDs
    max_length: int = 2000,
    db: Session = Depends(get_db)
):
    """Search for relevant context for a given topic"""
    try:
        doc_id_list = document_ids.split(",") if document_ids else None
        context = vector_service.get_relevant_context(
            db, topic, doc_id_list, max_length
        )
        
        return {
            "topic": topic,
            "document_ids": doc_id_list,
            "context": context,
            "context_length": len(context)
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/embeddings/update/{document_id}")
async def update_document_embeddings(
    document_id: str,
    target_chunks: int = 10,
    db: Session = Depends(get_db)
):
    """Update embeddings for a specific document"""
    try:
        chunks = vector_service.update_document_embeddings(db, document_id, target_chunks)
        return {
            "document_id": document_id,
            "chunks_created": len(chunks),
            "embedding_dimension": vector_service.embedding_dimension
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/generations")
async def get_question_generations(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Get question generation history"""
    try:
        query = db.query(QuestionGeneration)
        
        if user_id:
            # Note: You might need to add user_id to QuestionGeneration model
            pass
        
        if status:
            query = query.filter(QuestionGeneration.generation_status == status)
        
        generations = query.order_by(QuestionGeneration.created_at.desc()).limit(limit).all()
        
        return [
            {
                "generation_id": str(gen.id),
                "user_input": gen.user_input,
                "generation_status": gen.generation_status,
                "human_review_status": gen.human_review_status,
                "model_version": gen.model_version,
                "retry_count": gen.retry_count,
                "created_at": gen.created_at,
                "updated_at": gen.updated_at,
                "question_counts": gen.final_questions
            }
            for gen in generations
        ]
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/generations/{generation_id}")
async def get_generation_details(
    generation_id: str,
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific generation"""
    try:
        generation = db.query(QuestionGeneration).filter(
            QuestionGeneration.id == generation_id
        ).first()
        
        if not generation:
            raise HTTPException(status_code=404, detail="Generation not found")
        
        return {
            "generation_id": str(generation.id),
            "user_input": generation.user_input,
            "context_chunks": generation.context_chunks,
            "generation_parameters": generation.generation_parameters,
            "output_questions": generation.output_questions,
            "final_questions": generation.final_questions,
            "generation_status": generation.generation_status,
            "human_review_status": generation.human_review_status,
            "model_version": generation.model_version,
            "retry_count": generation.retry_count,
            "created_at": generation.created_at,
            "updated_at": generation.updated_at
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generations/{generation_id}/review")
async def review_generation(
    generation_id: str,
    request: ReviewRequest,
    db: Session = Depends(get_db)
):
    """Human review and approval of generated questions"""
    try:
        generation = db.query(QuestionGeneration).filter(
            QuestionGeneration.id == generation_id
        ).first()
        
        if not generation:
            raise HTTPException(status_code=404, detail="Generation not found")
        
        if request.action == "approve":
            generation.human_review_status = "approved"
            # Mark all associated questions as human validated
            from app.models import Question, Flashcard
            db.query(Question).filter(
                Question.document_id.in_([doc for doc in generation.generation_parameters.get("document_ids", [])])
            ).update({"human_validated": True})
            
            db.query(Flashcard).filter(
                Flashcard.document_id.in_([doc for doc in generation.generation_parameters.get("document_ids", [])])
            ).update({"human_validated": True})
            
        elif request.action == "reject":
            generation.human_review_status = "rejected"
            # Optionally delete associated questions
            
        elif request.action == "approve_selected":
            generation.human_review_status = "partially_approved"
            # Mark only selected questions as validated
            if request.selected_question_ids:
                from app.models import Question, Flashcard
                db.query(Question).filter(
                    Question.id.in_(request.selected_question_ids)
                ).update({"human_validated": True})
        
        # Store reviewer notes if provided
        if request.reviewer_notes:
            if not generation.generation_parameters:
                generation.generation_parameters = {}
            generation.generation_parameters["reviewer_notes"] = request.reviewer_notes
        
        generation.updated_at = gen_service.current_date_time()
        db.commit()
        
        return {
            "generation_id": generation_id,
            "action": request.action,
            "status": generation.human_review_status,
            "message": f"Generation {request.action}d successfully"
        }
        
    except Exception as e:
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# Original routes for backward compatibility
@router.get("/by-document/{document_id}")
async def get_quiz_by_document(document_id: str, db: Session = Depends(get_db)):
    try:
        questions = quiz_service.get_questions_by_document(db, document_id)
        
        return {
            "document_id": document_id,
            "quiz_questions": questions,
            "total_questions": len(questions)
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/flashcards/by-document/{document_id}")
async def get_flashcards_by_document(document_id: str, db: Session = Depends(get_db)):
    try:
        flashcards = quiz_service.get_flashcards_by_document(db, document_id)
    
        return {
            "document_id": document_id,
            "flashcards": flashcards,
            "total_flashcards": len(flashcards)
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
        
@router.delete("/by-document/{document_id}")
async def delete_quiz_by_document(document_id: str, db: Session = Depends(get_db)):
    try:
        quiz_service.delete_questions_by_document(db, document_id)
        return {"message": f"Quiz deleted for document {document_id}"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/flashcards/by-document/{document_id}")
async def delete_flashcards_by_document(document_id: str, db: Session = Depends(get_db)):
    try:
        quiz_service.delete_flashcards_by_document(db, document_id)
        return {"message": f"Flashcards deleted for document {document_id}"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate/url")
async def generate_quiz_from_url(
    url: str = Form(...), 
    user_id: str = Form(...),
    session_id: Optional[str] = Form(None),
    quiz_count: int = Form(15), 
    flashcard_count: int = Form(15), 
    target_chunks: int = Form(5),
    db: Session = Depends(get_db)
):
    return gen_service.generate_quiz_from_url_service(
        url=url,
        user_id=user_id,
        session_id=session_id,
        quiz_count=quiz_count,
        flashcard_count=flashcard_count,
        target_chunks=target_chunks,
        db=db,
    )

@router.post("/generate/file")
async def generate_quiz_from_file(
    file: UploadFile = File(...), 
    user_id: str = Form(...),
    session_id: Optional[str] = Form(None),
    quiz_count: int = Form(15),
    flashcard_count: int = Form(15), 
    target_chunks: int = Form(5),
    db: Session = Depends(get_db)
):
    return gen_service.generate_quiz_from_file_service(
        file=file,
        user_id=user_id,
        session_id=session_id,
        quiz_count=quiz_count,
        flashcard_count=flashcard_count,
        target_chunks=target_chunks,
        db=db,
    )