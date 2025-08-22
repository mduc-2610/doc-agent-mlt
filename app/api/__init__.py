from .document_routes import router as parse_router
from .question_routes import router as question_router
from .explain_routes import router as explain_router

__all__ = [
    "parse_router",
    "question_router",
    "explain_router"
]