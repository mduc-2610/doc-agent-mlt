from .document import *
from .question import *
from .tutor import *

__all__ = [
    "SessionResponse", "DocumentResponse", "SessionDetailResponse",
    "SessionCreateRequest", "SessionUpdateRequest", "UrlParseRequest",
    "FileParseRequest", "MessageResponse", "FlashcardResponse",
    "QuestionAnswerResponse", "QuestionResponse", "DocumentUploadBase",
    "DocumentFileUploadRequest", "DocumentUrlUploadRequest",
    "QuestionGenerationRequest", "ReviewRequest",
    # Tutor schemas
    "TutorSessionCreate", "TutorInteractionCreate", "TutorResponse",
    "TutorInteractionResponse", "TutorSessionResponse", "LearningProgressResponse",
    "ExplainConceptRequest", "FlashcardStudyRequest", "FlashcardStudyResponse",
    "QuestionPracticeRequest", "QuestionPracticeResponse", "UserQuestionRequest",
    "LearningPathRequest"
]