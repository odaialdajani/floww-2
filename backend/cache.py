"""
Redis caching layer for Confluence Decoder API responses.

Caches expensive computations like:
- GEX calculations (5-min TTL)
- Options chain data (1-min TTL)
- Spot prices (10-sec TTL)
- Alert summaries (30-sec TTL)
"""

import hashlib
import json
import logging
from functools import wraps

logger = logging.getLogger(__name__)

_redis_client = None


def get_redis_client():
    """Get the Redis client singleton."""
    return _redis_client


def cache_response(ttl: int = 60, key_prefix: str = "api"):
    """Decorator to cache API response in Redis."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            client = get_redis_client()
            if not client:
                return await func(*args, **kwargs)

            # Build cache key from function name and arguments
            cache_key = f"{key_prefix}:{func.__name__}"
            for arg in args:
                if isinstance(arg, str):
                    cache_key += f":{arg}"
            for k, v in sorted(kwargs.items()):
                cache_key += f":{k}={v}"

            # Hash long keys
            if len(cache_key) > 200:
                cache_key = f"{key_prefix}:{func.__name__}:{hashlib.md5(cache_key.encode()).hexdigest()}"

            try:
                # Try to get from cache
                cached = await client.get(cache_key)
                if cached:
                    logger.debug(f"Cache hit: {cache_key}")
                    return json.loads(cached)
            except Exception as e:
                logger.debug(f"Cache read error: {e}")

            # Call the actual function
            result = await func(*args, **kwargs)

            # Store in cache
            try:
                await client.setex(cache_key, ttl, json.dumps(result, default=str))
                logger.debug(f"Cache set: {cache_key} (TTL={ttl}s)")
            except Exception as e:
                logger.debug(f"Cache write error: {e}")

            return result
        return wrapper
    return decorator


