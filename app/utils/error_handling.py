# app/utils/error_handling.py - Simplified error handling
import functools
import time
import logging
import inspect
import traceback
from typing import Any, Callable, Optional, Type, Union
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError
from openai import OpenAIError, RateLimitError, APITimeoutError
from app.config import settings

logger = logging.getLogger(__name__)

class RetryableError(Exception):
    """Base class for errors that should be retried"""
    pass

class ValidationError(Exception):
    """Raised when data validation fails"""
    pass

def retry_on_exception(
    exceptions: Union[Type[Exception], tuple] = (RetryableError,),
    max_retries: int = None,
    base_delay: float = 1.0
):
    
    if max_retries is None:
        max_retries = settings.rag.max_retries
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(f"Function {func.__name__} failed after {max_retries} retries: {e}")
                        raise
                    
                    delay = base_delay * (2 ** attempt)  
                    logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}. Retrying in {delay:.2f}s")
                    time.sleep(delay)
                
                except Exception as e:
                    logger.error(f"Non-retryable error in {func.__name__}: {e}")
                    raise
            
            raise last_exception
        
        return wrapper
    return decorator

def exception_handler(mapping: dict[Type[Exception], tuple[int, str]], default_status=500, default_detail="Unexpected error"):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except tuple(mapping.keys()) as e:
                status, detail = mapping.get(type(e), (default_status, default_detail))
                logger.warning(f"{type(e).__name__} in {func.__name__}: {e}")
                raise HTTPException(status_code=status, detail=detail)
            except Exception as e:
                logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
                raise HTTPException(status_code=default_status, detail=default_detail)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except tuple(mapping.keys()) as e:
                status, detail = mapping.get(type(e), (default_status, default_detail))
                logger.warning(f"{type(e).__name__} in {func.__name__}: {e}")
                raise HTTPException(status_code=status, detail=detail)
            except Exception as e:
                logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
                raise HTTPException(status_code=default_status, detail=default_detail)

        return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper
    return decorator

handle_database_errors = exception_handler({
    IntegrityError: (400, "Data integrity violation"),
    OperationalError: (503, "Database temporarily unavailable"),
    SQLAlchemyError: (500, "Database error occurred"),
})

handle_llm_errors = exception_handler({
    RateLimitError: (429, "Rate limit exceeded. Please try again later."),
    APITimeoutError: (504, "Request timed out. Please try again."),
    OpenAIError: (502, "External service error. Please try again later."),
}, default_detail="An error occurred during content generation")

def validate_input(validation_func: Callable) -> Callable:    
    def decorator(func: Callable) -> Callable:
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                try:
                    validation_func(*args, **kwargs)
                    return await func(*args, **kwargs)
                except ValidationError as e:
                    logger.warning(f"Validation failed for {func.__name__}: {e}")
                    raise HTTPException(status_code=422, detail=str(e))
                except Exception as e:
                    logger.error(f"Error during validation for {func.__name__}: {e}")
                    raise
            return wrapper
        else:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    validation_func(*args, **kwargs)
                    return func(*args, **kwargs)
                except ValidationError as e:
                    logger.warning(f"Validation failed for {func.__name__}: {e}")
                    raise HTTPException(status_code=422, detail=str(e))
                except Exception as e:
                    logger.error(f"Error during validation for {func.__name__}: {e}")
                    raise
            return wrapper
    return decorator


def validate_document_request(**kwargs):
    file_size = kwargs.get('file_size')
    content_type = kwargs.get('content_type')
    
    if file_size and file_size > settings.max_file_size_mb * 1024 * 1024:
        raise ValidationError(f"File size exceeds maximum allowed size of {settings.max_file_size_mb}MB")
    
    allowed_types = {
        'application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/tiff',
        'audio/mpeg', 'audio/wav', 'audio/mp3', 'video/mp4', 'video/avi'
    }
    
    if content_type and content_type not in allowed_types:
        raise ValidationError(f"Unsupported file type: {content_type}")

def validate_question_generation_request(**kwargs):
    question_count = kwargs.get('question_count')
    topic = kwargs.get('topic')
    
    if question_count is not None:
        if question_count < 1 or question_count > 50:
            raise ValidationError("Question count must be between 1 and 50")
    
    if topic is not None:
        if len(topic.strip()) < 2:
            raise ValidationError("Topic must be at least 2 characters long")
        if len(topic) > 200:
            raise ValidationError("Topic must be less than 200 characters")

def validate_session_request(**kwargs):
    name = kwargs.get('name')
    description = kwargs.get('description')
    
    if name is not None:
        if len(name.strip()) < 1:
            raise ValidationError("Session name cannot be empty")
        if len(name) > 255:
            raise ValidationError("Session name must be less than 255 characters")
    
    if description is not None and len(description) > 1000:
        raise ValidationError("Session description must be less than 1000 characters")