"""Tests for cache backends."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.cache.base import CacheBackend, CacheEntry
from orchestrator.cache.memory import InMemoryCache
from orchestrator.cache.redis import RedisCache
from orchestrator.cache.factory import create_cache, get_cache, reset_cache


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_expires_at_with_ttl(self) -> None:
        """Test expires_at calculation with TTL."""
        entry = CacheEntry(
            key="test",
            value="data",
            created_at=datetime(2025, 1, 1, 12, 0, 0),
            ttl_seconds=3600,
        )
        expected = datetime(2025, 1, 1, 13, 0, 0)
        assert entry.expires_at == expected

    def test_expires_at_without_ttl(self) -> None:
        """Test expires_at returns None without TTL."""
        entry = CacheEntry(key="test", value="data", ttl_seconds=None)
        assert entry.expires_at is None

    def test_is_expired_true(self) -> None:
        """Test is_expired returns True for old entry."""
        entry = CacheEntry(
            key="test",
            value="data",
            created_at=datetime.utcnow() - timedelta(hours=2),
            ttl_seconds=3600,
        )
        assert entry.is_expired is True

    def test_is_expired_false(self) -> None:
        """Test is_expired returns False for fresh entry."""
        entry = CacheEntry(
            key="test",
            value="data",
            created_at=datetime.utcnow(),
            ttl_seconds=3600,
        )
        assert entry.is_expired is False

    def test_is_expired_no_ttl(self) -> None:
        """Test entry without TTL never expires."""
        entry = CacheEntry(
            key="test",
            value="data",
            created_at=datetime.utcnow() - timedelta(days=365),
            ttl_seconds=None,
        )
        assert entry.is_expired is False

    def test_age_seconds(self) -> None:
        """Test age_seconds calculation."""
        entry = CacheEntry(
            key="test",
            value="data",
            created_at=datetime.utcnow() - timedelta(seconds=100),
        )
        assert entry.age_seconds >= 100
        assert entry.age_seconds < 102  # Allow small time drift

    def test_ttl_remaining(self) -> None:
        """Test ttl_remaining calculation."""
        entry = CacheEntry(
            key="test",
            value="data",
            created_at=datetime.utcnow(),
            ttl_seconds=3600,
        )
        assert entry.ttl_remaining is not None
        assert entry.ttl_remaining > 3590
        assert entry.ttl_remaining <= 3600


class TestInMemoryCache:
    """Tests for InMemoryCache backend."""

    @pytest.fixture
    def cache(self) -> InMemoryCache:
        """Create a test cache instance."""
        return InMemoryCache(default_ttl_seconds=60)

    def test_name(self, cache: InMemoryCache) -> None:
        """Test backend name."""
        assert cache.name == "memory"

    def test_is_connected(self, cache: InMemoryCache) -> None:
        """Test connection status."""
        assert cache.is_connected is True

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache: InMemoryCache) -> None:
        """Test basic set and get operations."""
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_missing_key(self, cache: InMemoryCache) -> None:
        """Test get returns None for missing key."""
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_with_ttl(self, cache: InMemoryCache) -> None:
        """Test set with custom TTL."""
        await cache.set("key1", "value1", ttl_seconds=1)

        # Should exist immediately
        result = await cache.get("key1")
        assert result == "value1"

        # Wait for expiry
        await asyncio.sleep(1.1)

        # Should be expired
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, cache: InMemoryCache) -> None:
        """Test delete operation."""
        await cache.set("key1", "value1")
        deleted = await cache.delete("key1")
        assert deleted is True

        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, cache: InMemoryCache) -> None:
        """Test delete returns False for nonexistent key."""
        deleted = await cache.delete("nonexistent")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_exists(self, cache: InMemoryCache) -> None:
        """Test exists operation."""
        await cache.set("key1", "value1")
        assert await cache.exists("key1") is True
        assert await cache.exists("nonexistent") is False

    @pytest.mark.asyncio
    async def test_clear_all(self, cache: InMemoryCache) -> None:
        """Test clear all entries."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")

        count = await cache.clear()
        assert count == 3
        assert cache.size() == 0

    @pytest.mark.asyncio
    async def test_clear_with_pattern(self, cache: InMemoryCache) -> None:
        """Test clear with pattern matching."""
        await cache.set("user:1", "alice")
        await cache.set("user:2", "bob")
        await cache.set("config:timeout", "30")

        count = await cache.clear("user:*")
        assert count == 2

        assert await cache.exists("user:1") is False
        assert await cache.exists("config:timeout") is True

    @pytest.mark.asyncio
    async def test_get_many(self, cache: InMemoryCache) -> None:
        """Test batch get operation."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")

        result = await cache.get_many(["key1", "key2", "key4"])
        assert result == {"key1": "value1", "key2": "value2"}

    @pytest.mark.asyncio
    async def test_set_many(self, cache: InMemoryCache) -> None:
        """Test batch set operation."""
        items = {
            "key1": "value1",
            "key2": "value2",
            "key3": "value3",
        }
        count = await cache.set_many(items)
        assert count == 3

        for key, value in items.items():
            assert await cache.get(key) == value

    @pytest.mark.asyncio
    async def test_increment(self, cache: InMemoryCache) -> None:
        """Test increment operation."""
        # Increment nonexistent key
        result = await cache.increment("counter", 5)
        assert result == 5

        # Increment existing key
        result = await cache.increment("counter", 3)
        assert result == 8

        # Decrement
        result = await cache.increment("counter", -2)
        assert result == 6

    @pytest.mark.asyncio
    async def test_get_or_set_existing(self, cache: InMemoryCache) -> None:
        """Test get_or_set with existing value."""
        await cache.set("key1", "existing")

        result = await cache.get_or_set("key1", "new_value")
        assert result == "existing"

    @pytest.mark.asyncio
    async def test_get_or_set_missing(self, cache: InMemoryCache) -> None:
        """Test get_or_set with missing value."""
        result = await cache.get_or_set("key1", "computed_value")
        assert result == "computed_value"
        assert await cache.get("key1") == "computed_value"

    @pytest.mark.asyncio
    async def test_get_or_set_with_callable(self, cache: InMemoryCache) -> None:
        """Test get_or_set with factory function."""
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return f"computed_{call_count}"

        result1 = await cache.get_or_set("key1", factory)
        result2 = await cache.get_or_set("key1", factory)

        assert result1 == "computed_1"
        assert result2 == "computed_1"  # Should use cached value
        assert call_count == 1  # Factory only called once

    @pytest.mark.asyncio
    async def test_max_size_eviction(self) -> None:
        """Test eviction when max size is reached."""
        cache = InMemoryCache(default_ttl_seconds=60, max_size=3)

        await cache.set("key1", "value1")
        await asyncio.sleep(0.01)  # Ensure different timestamps
        await cache.set("key2", "value2")
        await asyncio.sleep(0.01)
        await cache.set("key3", "value3")
        await asyncio.sleep(0.01)

        # This should evict key1 (oldest)
        await cache.set("key4", "value4")

        assert cache.size() == 3
        assert await cache.exists("key1") is False
        assert await cache.exists("key4") is True

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, cache: InMemoryCache) -> None:
        """Test cleanup of expired entries."""
        await cache.set("short_lived", "value", ttl_seconds=1)
        await cache.set("long_lived", "value", ttl_seconds=3600)

        await asyncio.sleep(1.1)

        count = await cache.cleanup_expired()
        assert count == 1
        assert await cache.exists("short_lived") is False
        assert await cache.exists("long_lived") is True

    @pytest.mark.asyncio
    async def test_health_check(self, cache: InMemoryCache) -> None:
        """Test health check response."""
        await cache.set("key1", "value1")

        health = await cache.health_check()
        assert health["backend"] == "memory"
        assert health["connected"] is True
        assert health["total_entries"] == 1

    @pytest.mark.asyncio
    async def test_close(self, cache: InMemoryCache) -> None:
        """Test cache close operation."""
        await cache.set("key1", "value1")
        await cache.close()

        assert cache.is_connected is False
        assert cache.size() == 0


class TestRedisCache:
    """Tests for RedisCache backend."""

    @pytest.fixture
    def cache(self) -> RedisCache:
        """Create a test Redis cache instance."""
        return RedisCache(
            url="redis://localhost:6379/0",
            default_ttl_seconds=60,
            prefix="test:",
        )

    def test_name(self, cache: RedisCache) -> None:
        """Test backend name."""
        assert cache.name == "redis"

    def test_initial_connection_status(self, cache: RedisCache) -> None:
        """Test initial connection status is False."""
        assert cache.is_connected is False

    def test_get_key_prefix(self, cache: RedisCache) -> None:
        """Test key prefixing."""
        assert cache._get_key("mykey") == "test:mykey"

    def test_serialization(self, cache: RedisCache) -> None:
        """Test value serialization/deserialization."""
        test_data = {"name": "test", "value": 123, "nested": {"a": 1}}

        serialized = cache._serialize(test_data)
        assert isinstance(serialized, str)

        deserialized = cache._deserialize(serialized)
        assert deserialized == test_data

    def test_deserialize_invalid(self, cache: RedisCache) -> None:
        """Test deserialization of invalid data."""
        assert cache._deserialize(None) is None
        assert cache._deserialize("not json") is None
        assert cache._deserialize(b"not json") is None

    @pytest.mark.asyncio
    async def test_connect_success(self, cache: RedisCache) -> None:
        """Test successful connection (mocked)."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)

        with patch("redis.asyncio.from_url", return_value=mock_client):
            result = await cache.connect()

        assert result is True
        assert cache.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_failure(self, cache: RedisCache) -> None:
        """Test connection failure handling."""
        with patch("redis.asyncio.from_url", side_effect=Exception("Connection failed")):
            result = await cache.connect()

        assert result is False
        assert cache.is_connected is False

    @pytest.mark.asyncio
    async def test_get_success(self, cache: RedisCache) -> None:
        """Test get operation (mocked)."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.get = AsyncMock(return_value=b'{"v": "test_value", "t": "2025-01-01"}')

        with patch("redis.asyncio.from_url", return_value=mock_client):
            await cache.connect()
            result = await cache.get("mykey")

        assert result == "test_value"
        mock_client.get.assert_called_once_with("test:mykey")

    @pytest.mark.asyncio
    async def test_set_success(self, cache: RedisCache) -> None:
        """Test set operation (mocked)."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.setex = AsyncMock()

        with patch("redis.asyncio.from_url", return_value=mock_client):
            await cache.connect()
            result = await cache.set("mykey", "myvalue", ttl_seconds=120)

        assert result is True
        mock_client.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_success(self, cache: RedisCache) -> None:
        """Test delete operation (mocked)."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.delete = AsyncMock(return_value=1)

        with patch("redis.asyncio.from_url", return_value=mock_client):
            await cache.connect()
            result = await cache.delete("mykey")

        assert result is True

    @pytest.mark.asyncio
    async def test_exists_success(self, cache: RedisCache) -> None:
        """Test exists operation (mocked)."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.exists = AsyncMock(return_value=1)

        with patch("redis.asyncio.from_url", return_value=mock_client):
            await cache.connect()
            result = await cache.exists("mykey")

        assert result is True

    @pytest.mark.asyncio
    async def test_get_many_success(self, cache: RedisCache) -> None:
        """Test batch get operation (mocked)."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.mget = AsyncMock(return_value=[
            b'{"v": "value1", "t": "2025-01-01"}',
            b'{"v": "value2", "t": "2025-01-01"}',
            None,
        ])

        with patch("redis.asyncio.from_url", return_value=mock_client):
            await cache.connect()
            result = await cache.get_many(["key1", "key2", "key3"])

        assert result == {"key1": "value1", "key2": "value2"}

    @pytest.mark.asyncio
    async def test_set_many_success(self, cache: RedisCache) -> None:
        """Test batch set operation (mocked)."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_pipe = AsyncMock()
        mock_pipe.execute = AsyncMock(return_value=[True, True])
        mock_client.pipeline = MagicMock(return_value=mock_pipe)

        with patch("redis.asyncio.from_url", return_value=mock_client):
            await cache.connect()
            result = await cache.set_many({"key1": "value1", "key2": "value2"})

        assert result == 2

    @pytest.mark.asyncio
    async def test_health_check_connected(self, cache: RedisCache) -> None:
        """Test health check when connected (mocked)."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.info = AsyncMock(return_value={
            "redis_version": "7.0.0",
            "used_memory_human": "1M",
        })
        mock_client.dbsize = AsyncMock(return_value=100)

        with patch("redis.asyncio.from_url", return_value=mock_client):
            await cache.connect()
            health = await cache.health_check()

        assert health["backend"] == "redis"
        assert health["connected"] is True
        assert health["redis_version"] == "7.0.0"

    @pytest.mark.asyncio
    async def test_operations_when_disconnected(self, cache: RedisCache) -> None:
        """Test operations return gracefully when disconnected."""
        # Don't connect - should return None/False gracefully
        assert await cache.get("key") is None
        assert await cache.set("key", "value") is False
        assert await cache.delete("key") is False
        assert await cache.exists("key") is False


class TestCacheFactory:
    """Tests for cache factory functions."""

    def setup_method(self) -> None:
        """Reset cache before each test."""
        reset_cache()

    def teardown_method(self) -> None:
        """Reset cache after each test."""
        reset_cache()

    def test_create_memory_cache(self) -> None:
        """Test creating memory cache."""
        cache = create_cache(backend="memory")
        assert isinstance(cache, InMemoryCache)
        assert cache.name == "memory"

    def test_create_redis_cache_with_url(self) -> None:
        """Test creating Redis cache with URL."""
        with patch("orchestrator.cache.factory.settings") as mock_settings:
            mock_settings.cache_backend = "redis"
            mock_settings.redis_url = "redis://localhost:6379/0"
            mock_settings.redis_ttl_seconds = 3600
            mock_settings.redis_prefix = "test:"

            cache = create_cache(backend="redis")

        assert isinstance(cache, RedisCache)
        assert cache.name == "redis"

    def test_create_redis_falls_back_without_url(self) -> None:
        """Test Redis falls back to memory without URL."""
        with patch("orchestrator.cache.factory.settings") as mock_settings:
            mock_settings.cache_backend = "redis"
            mock_settings.redis_url = None
            mock_settings.redis_ttl_seconds = 3600

            cache = create_cache(backend="redis")

        assert isinstance(cache, InMemoryCache)

    def test_create_unknown_backend_raises(self) -> None:
        """Test unknown backend raises ValueError."""
        with pytest.raises(ValueError, match="Unknown cache backend"):
            create_cache(backend="unknown")

    def test_get_cache_singleton(self) -> None:
        """Test get_cache returns same instance."""
        with patch("orchestrator.cache.factory.settings") as mock_settings:
            mock_settings.cache_backend = "memory"
            mock_settings.redis_ttl_seconds = 3600

            cache1 = get_cache()
            cache2 = get_cache()

        assert cache1 is cache2

    def test_reset_cache(self) -> None:
        """Test reset_cache clears singleton."""
        with patch("orchestrator.cache.factory.settings") as mock_settings:
            mock_settings.cache_backend = "memory"
            mock_settings.redis_ttl_seconds = 3600

            cache1 = get_cache()
            reset_cache()
            cache2 = get_cache()

        assert cache1 is not cache2


class TestCacheConvenienceFunctions:
    """Tests for cache convenience functions."""

    def setup_method(self) -> None:
        """Reset cache before each test."""
        reset_cache()

    def teardown_method(self) -> None:
        """Reset cache after each test."""
        reset_cache()

    @pytest.mark.asyncio
    async def test_cache_model_rankings(self) -> None:
        """Test caching model rankings."""
        from orchestrator.cache.factory import (
            cache_model_rankings,
            get_cached_model_rankings,
        )

        with patch("orchestrator.cache.factory.settings") as mock_settings:
            mock_settings.cache_backend = "memory"
            mock_settings.redis_ttl_seconds = 3600

            rankings = [
                {"model": "gpt-4", "score": 0.95},
                {"model": "claude-3", "score": 0.92},
            ]

            result = await cache_model_rankings("quality", rankings)
            assert result is True

            cached = await get_cached_model_rankings("quality")
            assert cached == rankings

            missing = await get_cached_model_rankings("nonexistent")
            assert missing is None

    @pytest.mark.asyncio
    async def test_cache_adapter_response(self) -> None:
        """Test caching adapter responses."""
        from orchestrator.cache.factory import (
            cache_adapter_response,
            get_cached_adapter_response,
        )

        with patch("orchestrator.cache.factory.settings") as mock_settings:
            mock_settings.cache_backend = "memory"
            mock_settings.redis_ttl_seconds = 3600

            data = {"models": [{"id": "test-model"}]}

            result = await cache_adapter_response("openrouter", data)
            assert result is True

            cached = await get_cached_adapter_response("openrouter")
            assert cached == data

    @pytest.mark.asyncio
    async def test_invalidate_rankings(self) -> None:
        """Test invalidating cached rankings."""
        from orchestrator.cache.factory import (
            cache_model_rankings,
            get_cached_model_rankings,
            invalidate_rankings,
        )

        with patch("orchestrator.cache.factory.settings") as mock_settings:
            mock_settings.cache_backend = "memory"
            mock_settings.redis_ttl_seconds = 3600

            await cache_model_rankings("quality", [{"model": "test"}])
            await cache_model_rankings("speed", [{"model": "test2"}])

            # Invalidate specific profile
            count = await invalidate_rankings("quality")
            assert count == 1
            assert await get_cached_model_rankings("quality") is None
            assert await get_cached_model_rankings("speed") is not None

            # Invalidate all
            await cache_model_rankings("quality", [{"model": "test"}])
            count = await invalidate_rankings()
            assert count == 2
