"""Cache factory for creating cache instances based on configuration."""

import logging
from functools import lru_cache
from typing import Any

from orchestrator.cache.base import CacheBackend
from orchestrator.cache.memory import InMemoryCache
from orchestrator.cache.redis import RedisCache
from orchestrator.config import settings

logger = logging.getLogger(__name__)

# Global cache instance
_cache_instance: CacheBackend | None = None


def create_cache(
    backend: str | None = None,
    **kwargs: Any,
) -> CacheBackend:
    """
    Create a cache backend instance.

    Args:
        backend: Backend type ("memory" or "redis"), defaults to config
        **kwargs: Additional arguments passed to the backend

    Returns:
        CacheBackend instance

    Raises:
        ValueError: If backend type is unknown
    """
    backend_type = backend or settings.cache_backend

    if backend_type == "memory":
        return InMemoryCache(
            default_ttl_seconds=kwargs.get("ttl_seconds", settings.redis_ttl_seconds),
            max_size=kwargs.get("max_size"),
            cleanup_interval_seconds=kwargs.get("cleanup_interval", 300),
        )

    elif backend_type == "redis":
        if not settings.redis_url:
            logger.warning(
                "Redis URL not configured, falling back to in-memory cache. "
                "Set REDIS_URL environment variable to enable Redis caching."
            )
            return InMemoryCache(
                default_ttl_seconds=settings.redis_ttl_seconds,
            )

        return RedisCache(
            url=kwargs.get("url", settings.redis_url),
            default_ttl_seconds=kwargs.get("ttl_seconds", settings.redis_ttl_seconds),
            prefix=kwargs.get("prefix", settings.redis_prefix),
            max_connections=kwargs.get("max_connections", 10),
        )

    else:
        raise ValueError(f"Unknown cache backend: {backend_type}")


def get_cache() -> CacheBackend:
    """
    Get the global cache instance.

    Creates the cache on first access using configuration settings.
    This is the recommended way to access the cache in application code.

    Returns:
        CacheBackend instance
    """
    global _cache_instance

    if _cache_instance is None:
        _cache_instance = create_cache()
        logger.info(f"Initialized {_cache_instance.name} cache backend")

    return _cache_instance


async def initialize_cache() -> CacheBackend:
    """
    Initialize the global cache and establish connections.

    Call this during application startup to ensure the cache
    is ready before handling requests.

    Returns:
        Initialized CacheBackend instance
    """
    cache = get_cache()

    # Connect Redis if using Redis backend
    if isinstance(cache, RedisCache):
        connected = await cache.connect()
        if not connected:
            logger.warning("Failed to connect to Redis, using fallback memory cache")
            global _cache_instance
            _cache_instance = InMemoryCache(
                default_ttl_seconds=settings.redis_ttl_seconds,
            )
            return _cache_instance

    # Start cleanup task for in-memory cache
    if isinstance(cache, InMemoryCache):
        await cache.start_cleanup_task()

    return cache


async def shutdown_cache() -> None:
    """
    Shutdown the global cache and close connections.

    Call this during application shutdown for clean teardown.
    """
    global _cache_instance

    if _cache_instance is not None:
        await _cache_instance.close()
        _cache_instance = None
        logger.info("Cache shutdown complete")


def reset_cache() -> None:
    """
    Reset the global cache instance.

    Useful for testing or when configuration changes.
    """
    global _cache_instance
    _cache_instance = None


# Convenience functions for common caching patterns


async def cache_model_rankings(
    profile: str,
    rankings: list[dict[str, Any]],
    ttl_seconds: int | None = None,
) -> bool:
    """
    Cache model rankings for a routing profile.

    Args:
        profile: Routing profile name
        rankings: List of model rankings
        ttl_seconds: Cache TTL (defaults to config)

    Returns:
        True if cached successfully
    """
    cache = get_cache()
    key = f"rankings:{profile}"
    return await cache.set(key, rankings, ttl_seconds)


async def get_cached_model_rankings(profile: str) -> list[dict[str, Any]] | None:
    """
    Get cached model rankings for a routing profile.

    Args:
        profile: Routing profile name

    Returns:
        Cached rankings or None if not found
    """
    cache = get_cache()
    key = f"rankings:{profile}"
    return await cache.get(key)


async def cache_adapter_response(
    source: str,
    data: Any,
    ttl_seconds: int | None = None,
) -> bool:
    """
    Cache adapter response data.

    Args:
        source: Adapter source name
        data: Response data to cache
        ttl_seconds: Cache TTL

    Returns:
        True if cached successfully
    """
    cache = get_cache()
    key = f"adapter:{source}"
    return await cache.set(key, data, ttl_seconds)


async def get_cached_adapter_response(source: str) -> Any | None:
    """
    Get cached adapter response.

    Args:
        source: Adapter source name

    Returns:
        Cached data or None if not found
    """
    cache = get_cache()
    key = f"adapter:{source}"
    return await cache.get(key)


async def invalidate_rankings(profile: str | None = None) -> int:
    """
    Invalidate cached rankings.

    Args:
        profile: Specific profile to invalidate, or None for all

    Returns:
        Number of entries invalidated
    """
    cache = get_cache()
    if profile:
        deleted = await cache.delete(f"rankings:{profile}")
        return 1 if deleted else 0
    else:
        return await cache.clear("rankings:*")
