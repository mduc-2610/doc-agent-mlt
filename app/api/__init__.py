from .document_routes import router as parse_router
from .question_routes import router as question_router
from .summary_routes import router as summary_router

__all__ = [
    "parse_router",
    "question_router",
    "summary_router",
]