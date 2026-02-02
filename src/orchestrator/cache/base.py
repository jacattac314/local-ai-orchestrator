"""Abstract base class for cache backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class CacheEntry:
    """
    A cached value with metadata.

    Attributes:
        key: Cache key
        value: Cached data (JSON-serializable)
        created_at: When the entry was created
        ttl_seconds: Time-to-live in seconds (None = no expiry)
        metadata: Additional metadata
    """

    key: str
    value: Any
    created_at: datetime = field(default_factory=datetime.utcnow)
    ttl_seconds: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def expires_at(self) -> datetime | None:
        """Get expiration time, or None if no TTL."""
        if self.ttl_seconds is None:
            return None
        from datetime import timedelta
        return self.created_at + timedelta(seconds=self.ttl_seconds)

    @property
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def age_seconds(self) -> float:
        """Get age of entry in seconds."""
        return (datetime.utcnow() - self.created_at).total_seconds()

    @property
    def ttl_remaining(self) -> float | None:
        """Get remaining TTL in seconds, or None if no expiry."""
        if self.ttl_seconds is None:
            return None
        return max(0, self.ttl_seconds - self.age_seconds)


class CacheBackend(ABC):
    """
    Abstract base class for cache backends.

    Implement this class to add new cache storage backends
    (e.g., Redis, Memcached, etc.).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique identifier for this backend.

        Returns:
            Backend name (e.g., 'memory', 'redis')
        """
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if the backend is connected and healthy.

        Returns:
            True if connected, False otherwise
        """
        ...

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """
        Get a value from the cache.

        Args:
            key: Cache key

        Returns:
            Cached value, or None if not found/expired
        """
        ...

    @abstractmethod
    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> bool:
        """
        Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)
            ttl_seconds: Time-to-live in seconds (None = use default)

        Returns:
            True if successful, False otherwise
        """
        ...

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Delete a value from the cache.

        Args:
            key: Cache key

        Returns:
            True if deleted, False if not found
        """
        ...

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in the cache.

        Args:
            key: Cache key

        Returns:
            True if exists and not expired, False otherwise
        """
        ...

    @abstractmethod
    async def clear(self, pattern: str | None = None) -> int:
        """
        Clear cache entries.

        Args:
            pattern: Optional pattern to match keys (e.g., "model:*")
                    None = clear all entries

        Returns:
            Number of entries cleared
        """
        ...

    @abstractmethod
    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """
        Get multiple values from the cache.

        Args:
            keys: List of cache keys

        Returns:
            Dict mapping keys to values (missing keys omitted)
        """
        ...

    @abstractmethod
    async def set_many(
        self,
        items: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> int:
        """
        Set multiple values in the cache.

        Args:
            items: Dict mapping keys to values
            ttl_seconds: TTL for all items

        Returns:
            Number of items successfully set
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the cache connection."""
        ...

    async def get_or_set(
        self,
        key: str,
        factory: Any,
        ttl_seconds: int | None = None,
    ) -> Any:
        """
        Get a value, or compute and cache it if missing.

        Args:
            key: Cache key
            factory: Callable or coroutine that returns the value
            ttl_seconds: TTL if value needs to be computed

        Returns:
            Cached or computed value
        """
        value = await self.get(key)
        if value is not None:
            return value

        # Compute the value
        import asyncio
        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        elif callable(factory):
            value = factory()
        else:
            value = factory

        await self.set(key, value, ttl_seconds)
        return value

    async def increment(self, key: str, delta: int = 1) -> int:
        """
        Increment a numeric value.

        Args:
            key: Cache key
            delta: Amount to increment (can be negative)

        Returns:
            New value after increment
        """
        current = await self.get(key)
        if current is None:
            current = 0
        new_value = int(current) + delta
        await self.set(key, new_value)
        return new_value

    async def health_check(self) -> dict[str, Any]:
        """
        Perform a health check on the cache backend.

        Returns:
            Dict with health status info
        """
        return {
            "backend": self.name,
            "connected": self.is_connected,
        }
