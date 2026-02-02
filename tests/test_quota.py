"""Tests for quota management and rate limiting."""

import asyncio
import json
import os
import tempfile
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.quota.limiter import (
    RateLimitResult,
    SlidingWindowLimiter,
    TokenBucketLimiter,
)
from orchestrator.quota.manager import (
    QuotaConfig,
    QuotaManager,
    QuotaResult,
    QuotaStatus,
)


class TestRateLimitResult:
    """Tests for RateLimitResult dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        result = RateLimitResult(
            allowed=True,
            remaining=50,
            limit=100,
            reset_at=datetime(2025, 1, 1, 12, 0, 0),
            retry_after=None,
        )
        data = result.to_dict()

        assert data["allowed"] is True
        assert data["remaining"] == 50
        assert data["limit"] == 100
        assert data["reset_at"] == "2025-01-01T12:00:00"
        assert data["retry_after"] is None

    def test_to_dict_with_retry(self) -> None:
        """Test serialization with retry_after."""
        result = RateLimitResult(
            allowed=False,
            remaining=0,
            limit=100,
            reset_at=datetime(2025, 1, 1, 12, 0, 0),
            retry_after=30.5,
        )
        data = result.to_dict()

        assert data["allowed"] is False
        assert data["retry_after"] == 30.5


class TestSlidingWindowLimiter:
    """Tests for SlidingWindowLimiter."""

    @pytest.fixture
    def limiter(self) -> SlidingWindowLimiter:
        """Create a test limiter."""
        return SlidingWindowLimiter(limit=10, window_seconds=60)

    def test_name(self, limiter: SlidingWindowLimiter) -> None:
        """Test limiter name."""
        assert limiter.name == "sliding_window"

    @pytest.mark.asyncio
    async def test_check_initial_state(self, limiter: SlidingWindowLimiter) -> None:
        """Test check on fresh limiter."""
        result = await limiter.check("test_key")

        assert result.allowed is True
        assert result.remaining == 10
        assert result.limit == 10
        assert result.retry_after is None

    @pytest.mark.asyncio
    async def test_consume_success(self, limiter: SlidingWindowLimiter) -> None:
        """Test successful consumption."""
        result = await limiter.consume("test_key")

        assert result.allowed is True
        assert result.remaining == 9
        assert result.limit == 10

    @pytest.mark.asyncio
    async def test_consume_multiple(self, limiter: SlidingWindowLimiter) -> None:
        """Test multiple consumptions."""
        for i in range(5):
            result = await limiter.consume("test_key")
            assert result.allowed is True
            assert result.remaining == 10 - (i + 1)

    @pytest.mark.asyncio
    async def test_consume_exhausted(self, limiter: SlidingWindowLimiter) -> None:
        """Test behavior when limit exhausted."""
        # Exhaust the limit
        for _ in range(10):
            result = await limiter.consume("test_key")
            assert result.allowed is True

        # Next request should fail
        result = await limiter.consume("test_key")
        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after is not None
        assert result.retry_after > 0

    @pytest.mark.asyncio
    async def test_separate_keys(self, limiter: SlidingWindowLimiter) -> None:
        """Test that different keys have separate limits."""
        # Exhaust key1
        for _ in range(10):
            await limiter.consume("key1")

        # key2 should still have full quota
        result = await limiter.check("key2")
        assert result.allowed is True
        assert result.remaining == 10

    @pytest.mark.asyncio
    async def test_reset(self, limiter: SlidingWindowLimiter) -> None:
        """Test resetting a key."""
        # Consume some quota
        for _ in range(5):
            await limiter.consume("test_key")

        # Reset
        success = await limiter.reset("test_key")
        assert success is True

        # Should have full quota again
        result = await limiter.check("test_key")
        assert result.remaining == 10

    @pytest.mark.asyncio
    async def test_window_expiry(self) -> None:
        """Test that requests expire after window."""
        limiter = SlidingWindowLimiter(limit=5, window_seconds=1)

        # Exhaust limit
        for _ in range(5):
            await limiter.consume("test_key")

        result = await limiter.check("test_key")
        assert result.allowed is False

        # Wait for window to expire
        await asyncio.sleep(1.1)

        # Should be allowed again
        result = await limiter.check("test_key")
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_with_cache_backend(self) -> None:
        """Test limiter with cache backend."""
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        limiter = SlidingWindowLimiter(
            limit=10,
            window_seconds=60,
            cache=mock_cache,
        )

        await limiter.consume("test_key")

        # Should have tried to get and set from cache
        mock_cache.get.assert_called()
        mock_cache.set.assert_called()


class TestTokenBucketLimiter:
    """Tests for TokenBucketLimiter."""

    def test_name(self) -> None:
        """Test limiter name."""
        limiter = TokenBucketLimiter(capacity=10, refill_rate=1.0)
        assert limiter.name == "token_bucket"

    @pytest.mark.asyncio
    async def test_check_initial_state(self) -> None:
        """Test check on fresh limiter (full bucket)."""
        limiter = TokenBucketLimiter(capacity=10, refill_rate=1.0)
        result = await limiter.check("check_initial")

        assert result.allowed is True
        assert result.remaining == 10
        assert result.limit == 10

    @pytest.mark.asyncio
    async def test_consume_success(self) -> None:
        """Test successful token consumption."""
        limiter = TokenBucketLimiter(capacity=10, refill_rate=1.0)
        result = await limiter.consume("consume_success")

        assert result.allowed is True
        assert result.remaining == 9

    @pytest.mark.asyncio
    async def test_consume_multiple_tokens(self) -> None:
        """Test consuming multiple tokens at once."""
        limiter = TokenBucketLimiter(capacity=10, refill_rate=1.0)
        result = await limiter.consume("consume_multiple", tokens=5)

        assert result.allowed is True
        assert result.remaining == 5

    @pytest.mark.asyncio
    async def test_consume_exhausted(self) -> None:
        """Test behavior when tokens exhausted."""
        limiter = TokenBucketLimiter(capacity=10, refill_rate=1.0)
        # Exhaust all tokens
        result = await limiter.consume("consume_exhausted", tokens=10)
        assert result.allowed is True
        assert result.remaining == 0

        # Next request should fail
        result = await limiter.consume("consume_exhausted")
        assert result.allowed is False
        assert result.retry_after is not None

    @pytest.mark.asyncio
    async def test_token_refill(self) -> None:
        """Test that tokens refill over time."""
        limiter = TokenBucketLimiter(capacity=10, refill_rate=10.0)  # 10 tokens/sec

        # Consume all tokens
        await limiter.consume("refill_key", tokens=10)
        result = await limiter.check("refill_key")
        assert result.remaining == 0

        # Wait for refill
        await asyncio.sleep(0.5)  # Should refill ~5 tokens

        result = await limiter.check("refill_key")
        assert result.remaining >= 4  # Allow some timing variance

    @pytest.mark.asyncio
    async def test_burst_capacity(self) -> None:
        """Test that full burst capacity is available initially."""
        limiter = TokenBucketLimiter(capacity=10, refill_rate=1.0)
        # Should be able to consume full capacity at once
        result = await limiter.consume("burst_key", tokens=10)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_reset(self) -> None:
        """Test resetting bucket to full capacity."""
        limiter = TokenBucketLimiter(capacity=10, refill_rate=1.0)
        # Consume some tokens
        await limiter.consume("reset_key", tokens=8)

        # Reset
        success = await limiter.reset("reset_key")
        assert success is True

        # Should have full capacity
        result = await limiter.check("reset_key")
        assert result.remaining == 10


class TestQuotaConfig:
    """Tests for QuotaConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration."""
        config = QuotaConfig()
        assert config.requests_per_minute == 60
        assert config.requests_per_hour == 1000
        assert config.requests_per_day == 10000
        assert config.warning_threshold == 0.8
        assert config.enabled is True

    def test_custom_values(self) -> None:
        """Test custom configuration."""
        config = QuotaConfig(
            requests_per_minute=30,
            requests_per_hour=500,
            requests_per_day=5000,
            warning_threshold=0.9,
            enabled=False,
        )
        assert config.requests_per_minute == 30
        assert config.requests_per_hour == 500
        assert config.enabled is False

    def test_to_dict(self) -> None:
        """Test serialization."""
        config = QuotaConfig(requests_per_minute=100)
        data = config.to_dict()

        assert data["requests_per_minute"] == 100
        assert "requests_per_hour" in data
        assert "enabled" in data

    def test_from_dict(self) -> None:
        """Test deserialization."""
        data = {
            "requests_per_minute": 120,
            "requests_per_hour": 2000,
            "enabled": False,
        }
        config = QuotaConfig.from_dict(data)

        assert config.requests_per_minute == 120
        assert config.requests_per_hour == 2000
        assert config.enabled is False


class TestQuotaResult:
    """Tests for QuotaResult dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization."""
        result = QuotaResult(
            allowed=True,
            status=QuotaStatus.OK,
            reason="Within limits",
            minute_remaining=50,
            hour_remaining=900,
            day_remaining=9000,
            limits={"minute": 60, "hour": 1000, "day": 10000},
        )
        data = result.to_dict()

        assert data["allowed"] is True
        assert data["status"] == "ok"
        assert data["remaining"]["minute"] == 50
        assert data["limits"]["minute"] == 60


class TestQuotaStatus:
    """Tests for QuotaStatus enum."""

    def test_status_values(self) -> None:
        """Test enum values."""
        assert QuotaStatus.OK.value == "ok"
        assert QuotaStatus.WARNING.value == "warning"
        assert QuotaStatus.EXCEEDED.value == "exceeded"
        assert QuotaStatus.DISABLED.value == "disabled"


class TestQuotaManager:
    """Tests for QuotaManager."""

    @pytest.fixture
    def temp_config_path(self) -> str:
        """Create temporary config file path."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        yield path
        try:
            os.unlink(path)
        except OSError:
            pass

    @pytest.fixture
    def manager(self, temp_config_path: str) -> QuotaManager:
        """Create initialized quota manager."""
        manager = QuotaManager()
        manager.initialize(config_path=temp_config_path)
        return manager

    def test_initialize(self, temp_config_path: str) -> None:
        """Test manager initialization."""
        manager = QuotaManager()
        manager.initialize(config_path=temp_config_path)

        assert manager._initialized is True
        assert manager._minute_limiter is not None
        assert manager._hour_limiter is not None
        assert manager._day_limiter is not None

    def test_initialize_loads_config(self, temp_config_path: str) -> None:
        """Test loading existing config."""
        # Write config file
        config_data = {
            "requests_per_minute": 30,
            "requests_per_hour": 500,
            "enabled": True,
        }
        with open(temp_config_path, "w") as f:
            json.dump(config_data, f)

        manager = QuotaManager()
        manager.initialize(config_path=temp_config_path)

        assert manager.config.requests_per_minute == 30
        assert manager.config.requests_per_hour == 500

    def test_save_config(self, manager: QuotaManager, temp_config_path: str) -> None:
        """Test saving configuration."""
        manager.config.requests_per_minute = 120
        manager.save_config()

        with open(temp_config_path) as f:
            saved = json.load(f)

        assert saved["requests_per_minute"] == 120

    def test_update_config(self, manager: QuotaManager) -> None:
        """Test updating configuration."""
        updated = manager.update_config(
            requests_per_minute=30,
            enabled=False,
        )

        assert updated.requests_per_minute == 30
        assert updated.enabled is False
        # Others unchanged
        assert updated.requests_per_hour == 1000

    def test_update_config_clamps_values(self, manager: QuotaManager) -> None:
        """Test that update clamps invalid values."""
        manager.update_config(requests_per_minute=-10)
        assert manager.config.requests_per_minute == 0

        manager.update_config(warning_threshold=1.5)
        assert manager.config.warning_threshold == 1.0

    @pytest.mark.asyncio
    async def test_check_quota_disabled(self, temp_config_path: str) -> None:
        """Test quota check when disabled."""
        manager = QuotaManager()
        manager.initialize(config_path=temp_config_path)
        manager.config.enabled = False

        result = await manager.check_quota("user1")

        assert result.allowed is True
        assert result.status == QuotaStatus.DISABLED

    @pytest.mark.asyncio
    async def test_check_quota_ok(self, manager: QuotaManager) -> None:
        """Test quota check within limits."""
        result = await manager.check_quota("user1")

        assert result.allowed is True
        assert result.status == QuotaStatus.OK
        assert result.minute_remaining == 60
        assert result.hour_remaining == 1000
        assert result.day_remaining == 10000

    @pytest.mark.asyncio
    async def test_consume_quota(self, manager: QuotaManager) -> None:
        """Test consuming quota."""
        result = await manager.consume_quota("user1")

        assert result.allowed is True
        assert result.minute_remaining == 59
        assert result.hour_remaining == 999
        assert result.day_remaining == 9999

    @pytest.mark.asyncio
    async def test_consume_quota_exceeded(self, temp_config_path: str) -> None:
        """Test quota exceeded scenario."""
        manager = QuotaManager()
        manager.initialize(config_path=temp_config_path)
        manager.update_config(requests_per_minute=5)

        # Consume all quota
        for _ in range(5):
            result = await manager.consume_quota("user1")
            assert result.allowed is True

        # Next should fail
        result = await manager.consume_quota("user1")
        assert result.allowed is False
        assert result.status == QuotaStatus.EXCEEDED
        assert "minute" in result.reason.lower()
        assert result.retry_after is not None

    @pytest.mark.asyncio
    async def test_quota_warning_threshold(self, temp_config_path: str) -> None:
        """Test warning status when approaching limit."""
        manager = QuotaManager()
        manager.initialize(config_path=temp_config_path)
        manager.update_config(
            requests_per_minute=10,
            warning_threshold=0.8,
        )

        # Consume 80% of quota (8 requests)
        for _ in range(8):
            await manager.consume_quota("user1")

        # Check should show warning
        result = await manager.check_quota("user1")
        assert result.status == QuotaStatus.WARNING

    @pytest.mark.asyncio
    async def test_separate_user_quotas(self, manager: QuotaManager) -> None:
        """Test that different users have separate quotas."""
        # Consume some quota for user1
        for _ in range(10):
            await manager.consume_quota("user1")

        # user2 should have full quota
        result = await manager.check_quota("user2")
        assert result.minute_remaining == 60
        assert result.status == QuotaStatus.OK

    @pytest.mark.asyncio
    async def test_reset_quota(self, manager: QuotaManager) -> None:
        """Test resetting user quota."""
        # Consume some quota
        for _ in range(30):
            await manager.consume_quota("user1")

        result = await manager.check_quota("user1")
        assert result.minute_remaining == 30

        # Reset
        success = await manager.reset_quota("user1")
        assert success is True

        # Should have full quota
        result = await manager.check_quota("user1")
        assert result.minute_remaining == 60

    @pytest.mark.asyncio
    async def test_get_quota_status(self, manager: QuotaManager) -> None:
        """Test getting complete quota status."""
        # Consume some quota
        await manager.consume_quota("user1")

        status = await manager.get_quota_status("user1")

        assert status["identifier"] == "user1"
        assert "config" in status
        assert "usage" in status
        assert status["enabled"] is True
        assert status["config"]["requests_per_minute"] == 60

    @pytest.mark.asyncio
    async def test_disabled_windows(self, temp_config_path: str) -> None:
        """Test with some windows disabled (set to 0)."""
        manager = QuotaManager()
        manager.initialize(config_path=temp_config_path)
        manager.update_config(
            requests_per_minute=10,
            requests_per_hour=0,  # Disabled
            requests_per_day=0,   # Disabled
        )

        # Should only enforce minute limit
        result = await manager.check_quota("user1")
        assert result.minute_remaining == 10
        # Hour and day should show configured value (0)
        assert result.limits["hour"] == 0
        assert result.limits["day"] == 0

    @pytest.mark.asyncio
    async def test_with_cache_backend(self, temp_config_path: str) -> None:
        """Test manager with cache backend."""
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        manager = QuotaManager()
        manager.initialize(cache=mock_cache, config_path=temp_config_path)

        await manager.consume_quota("user1")

        # Cache should be used
        assert mock_cache.get.called or mock_cache.set.called


class TestQuotaConfigPersistence:
    """Tests for quota configuration persistence."""

    @pytest.fixture
    def temp_config_path(self) -> str:
        """Create temporary config file path."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        yield path
        try:
            os.unlink(path)
        except OSError:
            pass

    def test_config_persists(self, temp_config_path: str) -> None:
        """Test config persists across manager instances."""
        # First manager - set config
        manager1 = QuotaManager()
        manager1.initialize(config_path=temp_config_path)
        manager1.update_config(requests_per_minute=42)

        # Second manager - should load saved config
        manager2 = QuotaManager()
        manager2.initialize(config_path=temp_config_path)

        assert manager2.config.requests_per_minute == 42

    def test_handles_corrupted_config(self, temp_config_path: str) -> None:
        """Test graceful handling of corrupted config."""
        # Write invalid JSON
        with open(temp_config_path, "w") as f:
            f.write("not valid json {{{")

        manager = QuotaManager()
        manager.initialize(config_path=temp_config_path)

        # Should use defaults
        assert manager.config.requests_per_minute == 60


class TestConcurrentQuotaAccess:
    """Tests for concurrent quota access."""

    @pytest.mark.asyncio
    async def test_concurrent_consume(self) -> None:
        """Test concurrent quota consumption is thread-safe."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            config_path = f.name

        try:
            manager = QuotaManager()
            manager.initialize(config_path=config_path)
            manager.update_config(requests_per_minute=100)

            # Concurrently consume quota
            async def consume_many():
                results = []
                for _ in range(20):
                    result = await manager.consume_quota("concurrent_user")
                    results.append(result.allowed)
                return results

            # Run 5 concurrent tasks
            tasks = [consume_many() for _ in range(5)]
            all_results = await asyncio.gather(*tasks)

            # Flatten results
            all_allowed = [r for results in all_results for r in results]

            # Should have exactly 100 allowed (the limit)
            assert sum(all_allowed) == 100

        finally:
            try:
                os.unlink(config_path)
            except OSError:
                pass
