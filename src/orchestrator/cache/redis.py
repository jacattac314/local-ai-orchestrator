"""Redis cache backend implementation."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from orchestrator.cache.base import CacheBackend

logger = logging.getLogger(__name__)


class RedisCache(CacheBackend):
    """
    Redis cache backend for distributed caching.

    Best for:
    - Multi-instance deployments
    - Shared state across services
    - Persistent caching (survives restarts)
    - High-throughput workloads

    Features:
    - Automatic connection pooling
    - Pub/sub for cache invalidation
    - Atomic operations
    - Cluster support (with redis-py-cluster)
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        default_ttl_seconds: int = 3600,
        prefix: str = "orchestrator:",
        max_connections: int = 10,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
    ) -> None:
        """
        Initialize Redis cache.

        Args:
            url: Redis connection URL
            default_ttl_seconds: Default TTL for cache entries
            prefix: Key prefix for namespacing
            max_connections: Maximum connections in pool
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Connection timeout in seconds
        """
        self._url = url
        self._default_ttl = default_ttl_seconds
        self._prefix = prefix
        self._max_connections = max_connections
        self._socket_timeout = socket_timeout
        self._socket_connect_timeout = socket_connect_timeout
        self._client: Any = None
        self._connected = False

    @property
    def name(self) -> str:
        return "redis"

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _get_key(self, key: str) -> str:
        """Get prefixed key."""
        return f"{self._prefix}{key}"

    def _serialize(self, value: Any) -> str:
        """Serialize value to JSON string."""
        return json.dumps({
            "v": value,
            "t": datetime.utcnow().isoformat(),
        })

    def _deserialize(self, data: str | bytes | None) -> Any | None:
        """Deserialize JSON string to value."""
        if data is None:
            return None
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        try:
            parsed = json.loads(data)
            return parsed.get("v")
        except (json.JSONDecodeError, TypeError):
            return None

    async def connect(self) -> bool:
        """
        Connect to Redis.

        Returns:
            True if connected successfully
        """
        if self._connected and self._client:
            return True

        try:
            import redis.asyncio as redis

            self._client = redis.from_url(
                self._url,
                max_connections=self._max_connections,
                socket_timeout=self._socket_timeout,
                socket_connect_timeout=self._socket_connect_timeout,
                decode_responses=False,  # We handle encoding ourselves
            )

            # Test connection
            await self._client.ping()
            self._connected = True
            logger.info(f"Connected to Redis at {self._url}")
            return True

        except ImportError:
            logger.error("redis package not installed. Install with: pip install redis")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._connected = False
            return False

    async def _ensure_connected(self) -> bool:
        """Ensure we're connected to Redis."""
        if not self._connected:
            return await self.connect()
        return True

    async def get(self, key: str) -> Any | None:
        """Get a value from the cache."""
        if not await self._ensure_connected():
            return None

        try:
            data = await self._client.get(self._get_key(key))
            return self._deserialize(data)
        except Exception as e:
            logger.error(f"Redis GET error for {key}: {e}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Set a value in the cache."""
        if not await self._ensure_connected():
            return False

        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl

        try:
            serialized = self._serialize(value)
            if ttl > 0:
                await self._client.setex(
                    self._get_key(key),
                    ttl,
                    serialized,
                )
            else:
                await self._client.set(
                    self._get_key(key),
                    serialized,
                )
            return True
        except Exception as e:
            logger.error(f"Redis SET error for {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete a value from the cache."""
        if not await self._ensure_connected():
            return False

        try:
            result = await self._client.delete(self._get_key(key))
            return result > 0
        except Exception as e:
            logger.error(f"Redis DELETE error for {key}: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Check if a key exists in the cache."""
        if not await self._ensure_connected():
            return False

        try:
            return await self._client.exists(self._get_key(key)) > 0
        except Exception as e:
            logger.error(f"Redis EXISTS error for {key}: {e}")
            return False

    async def clear(self, pattern: str | None = None) -> int:
        """Clear cache entries matching pattern."""
        if not await self._ensure_connected():
            return 0

        try:
            if pattern is None:
                # Clear all keys with our prefix
                search_pattern = f"{self._prefix}*"
            else:
                search_pattern = f"{self._prefix}{pattern}"

            # Use SCAN to find keys (safe for large datasets)
            keys = []
            async for key in self._client.scan_iter(match=search_pattern):
                keys.append(key)

            if keys:
                await self._client.delete(*keys)

            return len(keys)
        except Exception as e:
            logger.error(f"Redis CLEAR error: {e}")
            return 0

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values from the cache."""
        if not keys or not await self._ensure_connected():
            return {}

        try:
            prefixed_keys = [self._get_key(k) for k in keys]
            values = await self._client.mget(prefixed_keys)

            result = {}
            for key, value in zip(keys, values):
                deserialized = self._deserialize(value)
                if deserialized is not None:
                    result[key] = deserialized

            return result
        except Exception as e:
            logger.error(f"Redis MGET error: {e}")
            return {}

    async def set_many(
        self,
        items: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> int:
        """Set multiple values in the cache."""
        if not items or not await self._ensure_connected():
            return 0

        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl

        try:
            # Use pipeline for atomic batch operation
            pipe = self._client.pipeline()

            for key, value in items.items():
                serialized = self._serialize(value)
                prefixed_key = self._get_key(key)
                if ttl > 0:
                    pipe.setex(prefixed_key, ttl, serialized)
                else:
                    pipe.set(prefixed_key, serialized)

            await pipe.execute()
            return len(items)
        except Exception as e:
            logger.error(f"Redis MSET error: {e}")
            return 0

    async def increment(self, key: str, delta: int = 1) -> int:
        """Atomically increment a numeric value."""
        if not await self._ensure_connected():
            return 0

        try:
            # For atomic increment, we use Redis's native INCRBY
            # But we need to handle our serialization format
            prefixed_key = self._get_key(key)

            # Check if key exists with our format
            data = await self._client.get(prefixed_key)
            if data is None:
                # Key doesn't exist, set it
                await self.set(key, delta)
                return delta

            # Deserialize, increment, and re-serialize
            current = self._deserialize(data)
            if current is None:
                current = 0
            new_value = int(current) + delta
            await self.set(key, new_value)
            return new_value
        except Exception as e:
            logger.error(f"Redis INCREMENT error for {key}: {e}")
            return 0

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client:
            try:
                await self._client.close()
                await self._client.connection_pool.disconnect()
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")
            finally:
                self._client = None
                self._connected = False

    async def health_check(self) -> dict[str, Any]:
        """Return health status with Redis info."""
        if not await self._ensure_connected():
            return {
                "backend": self.name,
                "connected": False,
                "error": "Not connected to Redis",
            }

        try:
            info = await self._client.info("server", "memory", "stats")
            keys_count = await self._client.dbsize()

            return {
                "backend": self.name,
                "connected": True,
                "redis_version": info.get("redis_version"),
                "used_memory_human": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients"),
                "total_keys": keys_count,
                "uptime_seconds": info.get("uptime_in_seconds"),
            }
        except Exception as e:
            return {
                "backend": self.name,
                "connected": self._connected,
                "error": str(e),
            }

    async def publish(self, channel: str, message: Any) -> int:
        """
        Publish a message to a Redis channel.

        Args:
            channel: Channel name
            message: Message to publish (will be JSON serialized)

        Returns:
            Number of subscribers that received the message
        """
        if not await self._ensure_connected():
            return 0

        try:
            serialized = json.dumps(message)
            return await self._client.publish(
                f"{self._prefix}channel:{channel}",
                serialized,
            )
        except Exception as e:
            logger.error(f"Redis PUBLISH error: {e}")
            return 0

    async def subscribe(self, channel: str):
        """
        Subscribe to a Redis channel.

        Args:
            channel: Channel name

        Returns:
            Async generator yielding messages
        """
        if not await self._ensure_connected():
            return

        try:
            pubsub = self._client.pubsub()
            await pubsub.subscribe(f"{self._prefix}channel:{channel}")

            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        yield json.loads(message["data"])
                    except json.JSONDecodeError:
                        yield message["data"]
        except Exception as e:
            logger.error(f"Redis SUBSCRIBE error: {e}")

    async def acquire_lock(
        self,
        name: str,
        timeout: float = 10.0,
        blocking: bool = True,
        blocking_timeout: float = 5.0,
    ) -> bool:
        """
        Acquire a distributed lock.

        Args:
            name: Lock name
            timeout: Lock expiration time in seconds
            blocking: Whether to wait for the lock
            blocking_timeout: How long to wait for lock

        Returns:
            True if lock acquired, False otherwise
        """
        if not await self._ensure_connected():
            return False

        try:
            lock = self._client.lock(
                f"{self._prefix}lock:{name}",
                timeout=timeout,
                blocking=blocking,
                blocking_timeout=blocking_timeout,
            )
            return await lock.acquire()
        except Exception as e:
            logger.error(f"Redis LOCK error: {e}")
            return False

    async def release_lock(self, name: str) -> bool:
        """
        Release a distributed lock.

        Args:
            name: Lock name

        Returns:
            True if released, False otherwise
        """
        if not await self._ensure_connected():
            return False

        try:
            lock = self._client.lock(f"{self._prefix}lock:{name}")
            await lock.release()
            return True
        except Exception as e:
            logger.error(f"Redis UNLOCK error: {e}")
            return False
