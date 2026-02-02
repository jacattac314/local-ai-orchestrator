"""In-memory cache backend implementation."""

import asyncio
import fnmatch
import logging
from datetime import datetime, timedelta
from typing import Any

from orchestrator.cache.base import CacheBackend, CacheEntry

logger = logging.getLogger(__name__)


class InMemoryCache(CacheBackend):
    """
    In-memory cache backend using a simple dictionary.

    Best for:
    - Single-instance deployments
    - Development and testing
    - Small to medium cache sizes

    Limitations:
    - Not shared across instances
    - Lost on restart
    - Grows with memory usage
    """

    def __init__(
        self,
        default_ttl_seconds: int = 3600,
        max_size: int | None = None,
        cleanup_interval_seconds: int = 300,
    ) -> None:
        """
        Initialize in-memory cache.

        Args:
            default_ttl_seconds: Default TTL for cache entries
            max_size: Maximum number of entries (None = unlimited)
            cleanup_interval_seconds: How often to clean expired entries
        """
        self._store: dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl_seconds
        self._max_size = max_size
        self._cleanup_interval = cleanup_interval_seconds
        self._cleanup_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._connected = True

    @property
    def name(self) -> str:
        return "memory"

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def get(self, key: str) -> Any | None:
        """Get a value from the cache."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None

            if entry.is_expired:
                del self._store[key]
                return None

            return entry.value

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Set a value in the cache."""
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl

        async with self._lock:
            # Evict if at max size
            if self._max_size and len(self._store) >= self._max_size:
                await self._evict_oldest()

            self._store[key] = CacheEntry(
                key=key,
                value=value,
                created_at=datetime.utcnow(),
                ttl_seconds=ttl,
            )
            return True

    async def delete(self, key: str) -> bool:
        """Delete a value from the cache."""
        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    async def exists(self, key: str) -> bool:
        """Check if a key exists in the cache."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False
            if entry.is_expired:
                del self._store[key]
                return False
            return True

    async def clear(self, pattern: str | None = None) -> int:
        """Clear cache entries matching pattern."""
        async with self._lock:
            if pattern is None:
                count = len(self._store)
                self._store.clear()
                return count

            # Match keys against pattern
            keys_to_delete = [
                k for k in self._store.keys()
                if fnmatch.fnmatch(k, pattern)
            ]
            for key in keys_to_delete:
                del self._store[key]
            return len(keys_to_delete)

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values from the cache."""
        result = {}
        async with self._lock:
            for key in keys:
                entry = self._store.get(key)
                if entry is not None and not entry.is_expired:
                    result[key] = entry.value
                elif entry is not None:
                    # Clean up expired entry
                    del self._store[key]
        return result

    async def set_many(
        self,
        items: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> int:
        """Set multiple values in the cache."""
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        count = 0

        async with self._lock:
            for key, value in items.items():
                # Evict if at max size
                if self._max_size and len(self._store) >= self._max_size:
                    await self._evict_oldest_unlocked()

                self._store[key] = CacheEntry(
                    key=key,
                    value=value,
                    created_at=datetime.utcnow(),
                    ttl_seconds=ttl,
                )
                count += 1

        return count

    async def close(self) -> None:
        """Close the cache and stop cleanup task."""
        self._connected = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        self._store.clear()

    async def _evict_oldest(self) -> None:
        """Evict the oldest entry (must hold lock)."""
        if not self._store:
            return

        oldest_key = min(
            self._store.keys(),
            key=lambda k: self._store[k].created_at
        )
        del self._store[oldest_key]

    async def _evict_oldest_unlocked(self) -> None:
        """Evict oldest entry without acquiring lock (caller must hold lock)."""
        if not self._store:
            return

        oldest_key = min(
            self._store.keys(),
            key=lambda k: self._store[k].created_at
        )
        del self._store[oldest_key]

    async def cleanup_expired(self) -> int:
        """Remove all expired entries."""
        async with self._lock:
            expired_keys = [
                k for k, v in self._store.items()
                if v.is_expired
            ]
            for key in expired_keys:
                del self._store[key]

            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

            return len(expired_keys)

    async def start_cleanup_task(self) -> None:
        """Start background task to periodically clean expired entries."""
        if self._cleanup_task is not None:
            return

        async def cleanup_loop():
            while self._connected:
                try:
                    await asyncio.sleep(self._cleanup_interval)
                    await self.cleanup_expired()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Cache cleanup error: {e}")

        self._cleanup_task = asyncio.create_task(cleanup_loop())

    async def health_check(self) -> dict[str, Any]:
        """Return health status with cache statistics."""
        async with self._lock:
            total_entries = len(self._store)
            expired_entries = sum(1 for v in self._store.values() if v.is_expired)

        return {
            "backend": self.name,
            "connected": self.is_connected,
            "total_entries": total_entries,
            "expired_entries": expired_entries,
            "max_size": self._max_size,
        }

    def size(self) -> int:
        """Get current number of entries (sync method for convenience)."""
        return len(self._store)
