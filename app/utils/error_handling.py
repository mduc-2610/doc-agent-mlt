# app/utils/error_handling.py
import functools
import time
import logging
import inspect
import traceback
from typing import Any, Callable, Optional, Type, Union, List, Dict
from fastapi import HTTPException
from app.schemas.document import SessionCreateRequest, SessionUpdateRequest
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError
from openai import OpenAIError, RateLimitError, APITimeoutError
from app.config import settings

logger = logging.getLogger(__name__)

class RetryableError(Exception):
    """Base class for errors that should be retried"""
    pass

class ProcessingError(Exception):
    """Base class for processing-related errors"""
    pass

class ValidationError(ProcessingError):
    """Raised when data validation fails"""
    pass

class ResourceError(ProcessingError):
    """Raised when external resources are unavailable"""
    pass

class ExponentialBackoff:
    """Implements exponential backoff with jitter"""
    
    def __init__(self, base_delay: float = 1.0, max_delay: float = 60.0, 
                 exponential_base: float = 2.0, jitter: bool = True):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number"""
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)
        
        if self.jitter:
            import random
            delay *= (0.5 + random.random() * 0.5)  # Add jitter between 50-100%
        
        return delay

def retry_on_exception(
    exceptions: Union[Type[Exception], tuple] = (RetryableError,),
    max_retries: int = None,
    backoff: Optional[ExponentialBackoff] = None,
    on_retry: Optional[Callable] = None
):
    """Decorator for retrying functions on specific exceptions"""
    
    if max_retries is None:
        max_retries = settings.rag.max_retries
    
    if backoff is None:
        backoff = ExponentialBackoff(base_delay=settings.rag.retry_delay_base)
    
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
                    
                    delay = backoff.calculate_delay(attempt)
                    logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}. Retrying in {delay:.2f}s")
                    
                    if on_retry:
                        on_retry(attempt, e)
                    
                    time.sleep(delay)
                
                except Exception as e:
                    # Non-retryable exception
                    logger.error(f"Non-retryable error in {func.__name__}: {e}")
                    raise
            
            # Should never reach here, but just in case
            raise last_exception
        
        return wrapper
    return decorator

def handle_database_errors(func: Callable) -> Callable:
    """Decorator for handling database-related errors (sync + async safe)"""

    if inspect.iscoroutinefunction(func):
        # async version
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)

            except IntegrityError as e:
                raise HTTPException(status_code=400, detail="Data integrity violation.")
            except OperationalError as e:
                raise HTTPException(status_code=503, detail="Database temporarily unavailable.")
            except SQLAlchemyError as e:
                raise HTTPException(status_code=500, detail="Database error occurred.")
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail="An unexpected error occurred.")
        return async_wrapper

    else:
        # sync version
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)

            except IntegrityError as e:
                raise HTTPException(status_code=400, detail="Data integrity violation.")
            except OperationalError as e:
                raise HTTPException(status_code=503, detail="Database temporarily unavailable.")
            except SQLAlchemyError as e:
                raise HTTPException(status_code=500, detail="Database error occurred.")
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail="An unexpected error occurred.")
        return sync_wrapper

def handle_llm_errors(func: Callable) -> Callable:
    """Decorator for handling LLM API errors (sync + async safe)"""

    if inspect.iscoroutinefunction(func):
        # async version
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)

            except RateLimitError as e:
                logger.warning(f"Rate limit hit in {func.__name__}: {e}")
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please try again in a few moments."
                )

            except APITimeoutError as e:
                logger.warning(f"API timeout in {func.__name__}: {e}")
                raise HTTPException(
                    status_code=504,
                    detail="Request timed out. Please try again."
                )

            except OpenAIError as e:
                logger.error(f"OpenAI API error in {func.__name__}: {e}")
                raise HTTPException(
                    status_code=502,
                    detail="External service error. Please try again later."
                )

            except Exception as e:
                logger.error(f"Unexpected error in LLM operation {func.__name__}: {e}")
                traceback.print_exc()
                raise HTTPException(
                    status_code=500,
                    detail="An error occurred during content generation."
                )
        return async_wrapper

    else:
        # sync version
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)

            except RateLimitError as e:
                logger.warning(f"Rate limit hit in {func.__name__}: {e}")
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please try again in a few moments."
                )

            except APITimeoutError as e:
                logger.warning(f"API timeout in {func.__name__}: {e}")
                raise HTTPException(
                    status_code=504,
                    detail="Request timed out. Please try again."
                )

            except OpenAIError as e:
                logger.error(f"OpenAI API error in {func.__name__}: {e}")
                raise HTTPException(
                    status_code=502,
                    detail="External service error. Please try again later."
                )

            except Exception as e:
                logger.error(f"Unexpected error in LLM operation {func.__name__}: {e}")
                traceback.print_exc()
                raise HTTPException(
                    status_code=500,
                    detail="An error occurred during content generation."
                )
        return sync_wrapper


def validate_input(validation_func: Callable) -> Callable:
    """Decorator for input validation (works for sync/async targets and validators)."""

    is_validator_async = inspect.iscoroutinefunction(validation_func)

    def decorator(func: Callable) -> Callable:
        if inspect.iscoroutinefunction(func):
            # async endpoint
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                try:
                    # run validation
                    if is_validator_async:
                        await validation_func(*args, **kwargs)
                    else:
                        validation_func(*args, **kwargs)

                    return await func(*args, **kwargs)

                except ValidationError as e:
                    # Return a 422 with structured detail if available
                    logger.warning(f"Validation failed for {func.__name__}: {e}")
                    detail = getattr(e, "errors", None)
                    detail = e.errors() if callable(detail) else str(e)
                    raise HTTPException(status_code=422, detail=detail)

                except HTTPException:
                    # Let FastAPI HTTP errors pass through unchanged
                    raise

                except Exception as e:
                    logger.exception(f"Error during validation for {func.__name__}: {e}")
                    # Re-raise so outer decorators/middleware can decide (don’t force a 500 here)
                    raise
            return wrapper

        else:
            # sync endpoint
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    if is_validator_async:
                        # If you *really* need async validation from a sync route, you could
                        # bridge with anyio.from_thread.run or similar. Simpler: require sync.
                        raise RuntimeError(
                            "Async validation_func used with sync endpoint. "
                            "Make validator sync or make endpoint async."
                        )
                    validation_func(*args, **kwargs)
                    return func(*args, **kwargs)

                except ValidationError as e:
                    logger.warning(f"Validation failed for {func.__name__}: {e}")
                    detail = getattr(e, "errors", None)
                    detail = e.errors() if callable(detail) else str(e)
                    raise HTTPException(status_code=422, detail=detail)

                except HTTPException:
                    raise

                except Exception as e:
                    logger.exception(f"Error during validation for {func.__name__}: {e}")
                    raise
            return wrapper

    return decorator
class ErrorCollector:
    
    def __init__(self, max_errors: int = 10):
        self.errors: List[Dict[str, Any]] = []
        self.max_errors = max_errors
        self.error_count = 0
    
    def add_error(self, operation: str, error: Exception, context: Dict[str, Any] = None):
        """Add an error to the collection"""
        self.error_count += 1
        
        error_info = {
            "operation": operation,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "timestamp": time.time(),
            "context": context or {}
        }
        
        if len(self.errors) < self.max_errors:
            self.errors.append(error_info)
        
        logger.error(f"Error in {operation}: {error}")
    
    def has_errors(self) -> bool:
        """Check if any errors were collected"""
        return self.error_count > 0
    
    def get_summary(self) -> Dict[str, Any]:
        """Get error summary"""
        return {
            "total_errors": self.error_count,
            "errors_shown": len(self.errors),
            "errors": self.errors
        }
    
    def should_fail_fast(self, error_threshold: float = 0.5, total_operations: int = 1) -> bool:
        """Determine if processing should stop due to error rate"""
        if total_operations == 0:
            return False
        
        error_rate = self.error_count / total_operations
        return error_rate > error_threshold

def safe_execute(operation: str, func: Callable, *args, 
                error_collector: Optional[ErrorCollector] = None, 
                context: Dict[str, Any] = None, **kwargs) -> Optional[Any]:
    """Safely execute a function and collect errors if needed"""
    try:
        return func(*args, **kwargs)
    
    except Exception as e:
        if error_collector:
            error_collector.add_error(operation, e, context)
        else:
            logger.error(f"Error in {operation}: {e}")
            traceback.print_exc()
        
        return None

# Specific validation functions
def validate_document_request(file_size: int = None, content_type: str = None, **kwargs):
    """Validate document upload request"""
    if file_size and file_size > settings.max_file_size_mb * 1024 * 1024:
        raise ValidationError(f"File size exceeds maximum allowed size of {settings.max_file_size_mb}MB")
    
    allowed_types = {
        'application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/tiff',
        'audio/mpeg', 'audio/wav', 'audio/mp3', 'video/mp4', 'video/avi'
    }
    
    if content_type and content_type not in allowed_types:
        raise ValidationError(f"Unsupported file type: {content_type}")

def validate_question_generation_request(question_count: int = None, topic: str = None, **kwargs):
    """Validate question generation request"""
    if question_count is not None:
        if question_count < 1 or question_count > 50:
            raise ValidationError("Question count must be between 1 and 50")
    
    if topic is not None:
        if len(topic.strip()) < 2:
            raise ValidationError("Topic must be at least 2 characters long")
        
        if len(topic) > 200:
            raise ValidationError("Topic must be less than 200 characters")

def validate_session_request(*args, **kwargs):
    request = None
    for arg in args:
        if isinstance(arg, (SessionCreateRequest, SessionUpdateRequest)):
            request = arg
            break
    if request is None:
        request = kwargs.get("request")

    if request is None:
        raise ValidationError("No request object provided")

    if request.name is not None:
        if len(request.name.strip()) < 1:
            raise ValidationError("Session name cannot be empty")
        if len(request.name) > 255:
            raise ValidationError("Session name must be less than 255 characters")

    if request.description is not None and len(request.description) > 1000:
        raise ValidationError("Session description must be less than 1000 characters")

ERROR_MAPPINGS = {
    "FileNotFoundError": {"status": 404, "message": "Requested file not found"},
    "PermissionError": {"status": 403, "message": "Insufficient permissions"},
    "TimeoutError": {"status": 504, "message": "Operation timed out"},
    "ConnectionError": {"status": 503, "message": "Service temporarily unavailable"},
    "ValidationError": {"status": 400, "message": "Invalid input data"},
    "ResourceError": {"status": 503, "message": "Required resource unavailable"}
}

def map_error_to_http(error: Exception) -> HTTPException:
    """Map internal errors to appropriate HTTP responses"""
    error_type = type(error).__name__
    
    if error_type in ERROR_MAPPINGS:
        mapping = ERROR_MAPPINGS[error_type]
        return HTTPException(
            status_code=mapping["status"],
            detail=mapping["message"]
        )
    
    # Default to 500 for unmapped errors
    logger.error(f"Unmapped error type: {error_type}: {error}")
    return HTTPException(
        status_code=500,
        detail="An unexpected error occurred"
    )