"""
Retry handler with exponential backoff.
"""

import time
import random
from typing import Callable, Any, Optional, TypeVar
from dataclasses import dataclass
from functools import wraps


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    initial_delay: float = 1.0
    max_delay: float = 10.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple = (Exception,)


T = TypeVar('T')


class RetryHandler:
    """Handles retry logic with exponential backoff."""
    
    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
    
    def retry(self, func: Callable[..., T]) -> Callable[..., T]:
        """
        Decorator to add retry logic to a function.
        
        Args:
            func: Function to retry
            
        Returns:
            Wrapped function with retry logic
        """
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            attempt = 0
            last_exception = None
            
            while attempt < self.config.max_attempts:
                try:
                    return func(*args, **kwargs)
                except self.config.retryable_exceptions as e:
                    attempt += 1
                    
                    if attempt >= self.config.max_attempts:
                        raise
                    
                    last_exception = e
                    delay = self._calculate_delay(attempt)
                    
                    self._log_retry(attempt, delay, str(e))
                    time.sleep(delay)
            
            raise last_exception or Exception("Max retries exceeded")
        
        return wrapper
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for current attempt."""
        delay = self.config.initial_delay * (self.config.exponential_base ** (attempt - 1))
        
        if self.config.jitter:
            delay *= random.uniform(0.5, 1.0)
        
        return min(delay, self.config.max_delay)
    
    def _log_retry(self, attempt: int, delay: float, error: str):
        """Log retry attempt."""
        print(f"⚠ Retry {attempt}/{self.config.max_attempts} in {delay:.2f}s: {error}")


def with_rate_limit(delay: float = 1.0):
    """
    Decorator to add rate limiting to a function.
    
    Args:
        delay: Delay in seconds between calls
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        last_call = 0
        
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            nonlocal last_call
            now = time.time()
            
            if now - last_call >= delay:
                last_call = now
                return func(*args, **kwargs)
            else:
                sleep_time = delay - (now - last_call)
                time.sleep(sleep_time)
                last_call = time.time()
                return func(*args, **kwargs)
        
        return wrapper
    return decorator
