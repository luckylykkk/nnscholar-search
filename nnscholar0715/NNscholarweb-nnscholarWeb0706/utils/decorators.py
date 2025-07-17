"""Utility decorators for the application."""

import functools
import time
import logging
from typing import Any, Callable, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def cache_result(ttl: int = 3600):
    """Cache function results with TTL (Time To Live)."""
    def decorator(func: Callable) -> Callable:
        cache: Dict[str, Dict[str, Any]] = {}
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from arguments
            cache_key = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            
            # Check if result is in cache and not expired
            if cache_key in cache:
                cached_data = cache[cache_key]
                if datetime.now() < cached_data['expires']:
                    logger.debug(f"Cache hit for {func.__name__}")
                    return cached_data['result']
                else:
                    # Remove expired entry
                    del cache[cache_key]
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache[cache_key] = {
                'result': result,
                'expires': datetime.now() + timedelta(seconds=ttl)
            }
            logger.debug(f"Cache miss for {func.__name__}, result cached")
            return result
        
        # Add cache management methods
        def clear_cache():
            cache.clear()
            logger.debug(f"Cache cleared for {func.__name__}")
        
        def get_cache_stats():
            return {
                'size': len(cache),
                'keys': list(cache.keys())
            }
        
        wrapper.clear_cache = clear_cache
        wrapper.get_cache_stats = get_cache_stats
        
        return wrapper
    return decorator

def rate_limit(max_calls: int = 60, window: int = 60):
    """Rate limiting decorator."""
    def decorator(func: Callable) -> Callable:
        calls = []
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            
            # Remove old calls outside the window
            calls[:] = [call_time for call_time in calls if now - call_time < window]
            
            if len(calls) >= max_calls:
                raise Exception(f"Rate limit exceeded: {max_calls} calls per {window} seconds")
            
            calls.append(now)
            return func(*args, **kwargs)
        
        return wrapper
    return decorator

def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Retry decorator with exponential backoff."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}")
                    
                    if attempt < max_attempts - 1:
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"All {max_attempts} attempts failed for {func.__name__}")
                        raise last_exception
            
            # This should never be reached, but just in case
            raise last_exception
        
        return wrapper
    return decorator

def log_execution(level: str = 'INFO'):
    """Log function execution time and parameters."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            # Log function start
            logger.log(getattr(logging, level), f"Executing {func.__name__}")
            
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                # Log success
                logger.log(getattr(logging, level), 
                          f"Completed {func.__name__} in {execution_time:.3f}s")
                
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                
                # Log failure
                logger.error(f"Failed {func.__name__} after {execution_time:.3f}s: {e}")
                raise
        
        return wrapper
    return decorator

def validate_params(**validators):
    """Validate function parameters."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            import inspect
            
            # Get function signature
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            
            # Validate parameters
            for param_name, validator in validators.items():
                if param_name in bound_args.arguments:
                    value = bound_args.arguments[param_name]
                    if not validator(value):
                        raise ValueError(f"Invalid value for parameter {param_name}: {value}")
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator

def singleton(cls):
    """Singleton decorator for classes."""
    instances = {}
    
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    
    return get_instance

def deprecated(reason: str = "This function is deprecated"):
    """Mark function as deprecated."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            import warnings
            warnings.warn(f"{func.__name__} is deprecated: {reason}", 
                         DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)
        
        return wrapper
    return decorator