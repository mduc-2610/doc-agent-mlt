from pydantic import BaseModel


class MessageResponse(BaseModel):
    """
    Standard message response with i18n support.
    
    Attributes:
        translation_key: The i18n key for the frontend to translate
        message: The original message text (kept for reference)
    """
    translation_key: str
    message: str
    
    @classmethod
    def create(cls, translation_key: str, message: str) -> "MessageResponse":
        """Create a message response with both translation key and message."""
        return cls(translation_key=translation_key, message=message)
