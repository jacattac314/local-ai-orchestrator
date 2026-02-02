"""
Cache module for distributed caching support.

Provides pluggable cache backends (in-memory and Redis) for
sharing state across multiple orchestrator instances.
"""

from orchestrator.cache.base import CacheBackend, CacheEntry
from orchestrator.cache.memory import InMemoryCache
from orchestrator.cache.redis import RedisCache
from orchestrator.cache.factory import get_cache, create_cache

__all__ = [
    "CacheBackend",
    "CacheEntry",
    "InMemoryCache",
    "RedisCache",
    "get_cache",
    "create_cache",
]
