"""Cache utilities for improving performance."""

import time
import hashlib
from typing import Any, Dict, Optional, Callable
from functools import wraps
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MemoryCache:
    """Simple in-memory cache with TTL support."""
    
    def __init__(self, default_ttl: int = 3600, max_size: int = 1000):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.default_ttl = default_ttl
        self.max_size = max_size
        self.access_times: Dict[str, float] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache.
        
        Args:
            key: Cache key
        
        Returns:
            Cached value or None if not found/expired
        """
        if key not in self.cache:
            return None
        
        entry = self.cache[key]
        
        # Check if expired
        if time.time() > entry['expires_at']:
            self.delete(key)
            return None
        
        # Update access time
        self.access_times[key] = time.time()
        
        return entry['value']
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
        
        Returns:
            True if value was cached successfully
        """
        try:
            # Use default TTL if not specified
            if ttl is None:
                ttl = self.default_ttl
            
            # Check if cache is full
            if len(self.cache) >= self.max_size and key not in self.cache:
                self._evict_lru()
            
            expires_at = time.time() + ttl
            
            self.cache[key] = {
                'value': value,
                'expires_at': expires_at,
                'created_at': time.time()
            }
            
            self.access_times[key] = time.time()
            
            return True
            
        except Exception as e:
            logger.error(f"Error setting cache key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from cache.
        
        Args:
            key: Cache key to delete
        
        Returns:
            True if key was deleted
        """
        try:
            if key in self.cache:
                del self.cache[key]
            if key in self.access_times:
                del self.access_times[key]
            return True
        except Exception as e:
            logger.error(f"Error deleting cache key {key}: {e}")
            return False
    
    def clear(self) -> bool:
        """Clear all cache entries.
        
        Returns:
            True if cache was cleared
        """
        try:
            self.cache.clear()
            self.access_times.clear()
            return True
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False
    
    def cleanup_expired(self) -> int:
        """Remove expired entries from cache.
        
        Returns:
            Number of entries removed
        """
        current_time = time.time()
        expired_keys = []
        
        for key, entry in self.cache.items():
            if current_time > entry['expires_at']:
                expired_keys.append(key)
        
        for key in expired_keys:
            self.delete(key)
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
        
        return len(expired_keys)
    
    def _evict_lru(self) -> bool:
        """Evict least recently used entry.
        
        Returns:
            True if an entry was evicted
        """
        if not self.access_times:
            return False
        
        # Find least recently used key
        lru_key = min(self.access_times.keys(), 
                     key=lambda k: self.access_times[k])
        
        self.delete(lru_key)
        logger.debug(f"Evicted LRU cache entry: {lru_key}")
        
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache stats
        """
        current_time = time.time()
        expired_count = sum(1 for entry in self.cache.values() 
                          if current_time > entry['expires_at'])
        
        return {
            'total_entries': len(self.cache),
            'expired_entries': expired_count,
            'active_entries': len(self.cache) - expired_count,
            'max_size': self.max_size,
            'default_ttl': self.default_ttl
        }


# Global cache instance
_global_cache = MemoryCache()


def get_cache_key(*args, **kwargs) -> str:
    """Generate cache key from arguments.
    
    Args:
        *args: Positional arguments
        **kwargs: Keyword arguments
    
    Returns:
        MD5 hash as cache key
    """
    # Convert arguments to string
    key_parts = [str(arg) for arg in args]
    
    # Add sorted kwargs
    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}={v}")
    
    key_string = "|".join(key_parts)
    
    # Generate MD5 hash
    return hashlib.md5(key_string.encode('utf-8')).hexdigest()


def cache_result(ttl: int = 3600, key_func: Optional[Callable] = None):
    """Decorator to cache function results.
    
    Args:
        ttl: Time to live in seconds
        key_func: Custom function to generate cache key
    
    Returns:
        Decorated function
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{get_cache_key(*args, **kwargs)}"
            
            # Try to get from cache
            result = _global_cache.get(cache_key)
            if result is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return result
            
            # Execute function
            logger.debug(f"Cache miss for {func.__name__}")
            result = func(*args, **kwargs)
            
            # Cache result if not None
            if result is not None:
                _global_cache.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator


def invalidate_cache_pattern(pattern: str) -> int:
    """Invalidate cache keys matching pattern.
    
    Args:
        pattern: Pattern to match (simple string contains)
    
    Returns:
        Number of keys invalidated
    """
    keys_to_delete = []
    
    for key in _global_cache.cache.keys():
        if pattern in key:
            keys_to_delete.append(key)
    
    for key in keys_to_delete:
        _global_cache.delete(key)
    
    if keys_to_delete:
        logger.info(f"Invalidated {len(keys_to_delete)} cache keys matching '{pattern}'")
    
    return len(keys_to_delete)


def get_global_cache() -> MemoryCache:
    """Get global cache instance.
    
    Returns:
        Global cache instance
    """
    return _global_cache


def clear_global_cache() -> bool:
    """Clear global cache.
    
    Returns:
        True if cache was cleared
    """
    return _global_cache.clear()


def cleanup_global_cache() -> int:
    """Cleanup expired entries in global cache.
    
    Returns:
        Number of entries cleaned up
    """
    return _global_cache.cleanup_expired()


def get_cache_stats() -> Dict[str, Any]:
    """Get global cache statistics.
    
    Returns:
        Cache statistics
    """
    return _global_cache.get_stats()


class RateLimiter:
    """Simple rate limiter using token bucket algorithm."""
    
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, list] = {}
    
    def is_allowed(self, key: str) -> bool:
        """Check if request is allowed for given key.
        
        Args:
            key: Identifier for rate limiting (e.g., user ID, IP)
        
        Returns:
            True if request is allowed
        """
        current_time = time.time()
        
        if key not in self.requests:
            self.requests[key] = []
        
        # Remove old requests outside the window
        self.requests[key] = [
            req_time for req_time in self.requests[key]
            if current_time - req_time < self.window_seconds
        ]
        
        # Check if under limit
        if len(self.requests[key]) < self.max_requests:
            self.requests[key].append(current_time)
            return True
        
        return False
    
    def get_remaining(self, key: str) -> int:
        """Get remaining requests for key.
        
        Args:
            key: Identifier for rate limiting
        
        Returns:
            Number of remaining requests
        """
        current_time = time.time()
        
        if key not in self.requests:
            return self.max_requests
        
        # Remove old requests
        self.requests[key] = [
            req_time for req_time in self.requests[key]
            if current_time - req_time < self.window_seconds
        ]
        
        return max(0, self.max_requests - len(self.requests[key]))
    
    def reset(self, key: str) -> bool:
        """Reset rate limit for key.
        
        Args:
            key: Identifier to reset
        
        Returns:
            True if reset was successful
        """
        if key in self.requests:
            del self.requests[key]
        return True