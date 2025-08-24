from .document_routes import router as parse_router
from .question_routes import router as question_router
from .tutor_routes import router as tutor_router

__all__ = [
    "parse_router",
    "question_router",
    "tutor_router",
]