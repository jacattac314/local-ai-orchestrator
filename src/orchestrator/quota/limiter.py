"""
Rate limiting algorithms for quota management.

Provides multiple rate limiting strategies:
- Sliding Window: Smooth rate limiting with partial window counting
- Token Bucket: Burst-friendly limiting with token replenishment
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import asyncio
import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    """Whether the request is allowed."""

    remaining: int
    """Remaining requests in the current window."""

    limit: int
    """Maximum requests allowed in the window."""

    reset_at: datetime
    """When the rate limit window resets."""

    retry_after: float | None = None
    """Seconds to wait before retrying (if not allowed)."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "remaining": self.remaining,
            "limit": self.limit,
            "reset_at": self.reset_at.isoformat(),
            "retry_after": self.retry_after,
        }


class RateLimiter(ABC):
    """Abstract base class for rate limiters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Limiter algorithm name."""
        ...

    @abstractmethod
    async def check(self, key: str) -> RateLimitResult:
        """
        Check if a request is allowed without consuming quota.

        Args:
            key: Unique identifier for the rate limit bucket

        Returns:
            RateLimitResult with current state
        """
        ...

    @abstractmethod
    async def consume(self, key: str, tokens: int = 1) -> RateLimitResult:
        """
        Consume quota for a request.

        Args:
            key: Unique identifier for the rate limit bucket
            tokens: Number of tokens to consume (default 1)

        Returns:
            RateLimitResult after consuming
        """
        ...

    @abstractmethod
    async def reset(self, key: str) -> bool:
        """
        Reset the rate limit for a key.

        Args:
            key: Unique identifier for the rate limit bucket

        Returns:
            True if reset successful
        """
        ...


class SlidingWindowLimiter(RateLimiter):
    """
    Sliding window rate limiter.

    Provides smooth rate limiting by counting requests in a sliding
    time window. More accurate than fixed windows at period boundaries.

    Uses cache backend for distributed state when available.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: int,
        cache: Any = None,
        key_prefix: str = "ratelimit:sw:",
    ) -> None:
        """
        Initialize sliding window limiter.

        Args:
            limit: Maximum requests per window
            window_seconds: Window size in seconds
            cache: Cache backend (uses in-memory if None)
            key_prefix: Prefix for cache keys
        """
        self._limit = limit
        self._window_seconds = window_seconds
        self._cache = cache
        self._key_prefix = key_prefix
        self._local_store: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "sliding_window"

    def _get_cache_key(self, key: str) -> str:
        return f"{self._key_prefix}{key}"

    async def _get_timestamps(self, key: str) -> list[float]:
        """Get request timestamps from cache or local store."""
        if self._cache:
            try:
                data = await self._cache.get(self._get_cache_key(key))
                if data:
                    return data
            except Exception as e:
                logger.warning(f"Cache error in rate limiter: {e}")

        return self._local_store.get(key, [])

    async def _set_timestamps(self, key: str, timestamps: list[float]) -> None:
        """Store timestamps in cache or local store."""
        if self._cache:
            try:
                await self._cache.set(
                    self._get_cache_key(key),
                    timestamps,
                    ttl_seconds=self._window_seconds + 60,
                )
            except Exception as e:
                logger.warning(f"Cache error in rate limiter: {e}")

        self._local_store[key] = timestamps

    def _clean_timestamps(self, timestamps: list[float], now: float) -> list[float]:
        """Remove timestamps outside the current window."""
        cutoff = now - self._window_seconds
        return [ts for ts in timestamps if ts > cutoff]

    async def check(self, key: str) -> RateLimitResult:
        """Check rate limit without consuming."""
        now = time.time()
        timestamps = await self._get_timestamps(key)
        timestamps = self._clean_timestamps(timestamps, now)

        count = len(timestamps)
        remaining = max(0, self._limit - count)
        allowed = count < self._limit

        # Calculate reset time (when oldest request falls out of window)
        if timestamps:
            oldest = min(timestamps)
            reset_at = datetime.utcfromtimestamp(oldest + self._window_seconds)
        else:
            reset_at = datetime.utcfromtimestamp(now + self._window_seconds)

        retry_after = None
        if not allowed and timestamps:
            retry_after = (oldest + self._window_seconds) - now

        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            limit=self._limit,
            reset_at=reset_at,
            retry_after=retry_after,
        )

    async def consume(self, key: str, tokens: int = 1) -> RateLimitResult:
        """Consume quota for a request."""
        async with self._lock:
            now = time.time()
            timestamps = await self._get_timestamps(key)
            timestamps = self._clean_timestamps(timestamps, now)

            count = len(timestamps)

            if count + tokens <= self._limit:
                # Add new timestamps for consumed tokens
                for _ in range(tokens):
                    timestamps.append(now)
                await self._set_timestamps(key, timestamps)

                remaining = self._limit - len(timestamps)
                return RateLimitResult(
                    allowed=True,
                    remaining=remaining,
                    limit=self._limit,
                    reset_at=datetime.utcfromtimestamp(now + self._window_seconds),
                    retry_after=None,
                )
            else:
                # Rate limit exceeded
                oldest = min(timestamps) if timestamps else now
                reset_at = datetime.utcfromtimestamp(oldest + self._window_seconds)
                retry_after = (oldest + self._window_seconds) - now

                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    limit=self._limit,
                    reset_at=reset_at,
                    retry_after=max(0, retry_after),
                )

    async def reset(self, key: str) -> bool:
        """Reset rate limit for a key."""
        if self._cache:
            try:
                await self._cache.delete(self._get_cache_key(key))
            except Exception as e:
                logger.warning(f"Cache error in rate limiter reset: {e}")

        self._local_store.pop(key, None)
        return True


class TokenBucketLimiter(RateLimiter):
    """
    Token bucket rate limiter.

    Allows bursts up to bucket capacity while maintaining
    average rate. Tokens replenish over time.

    Uses cache backend for distributed state when available.
    """

    def __init__(
        self,
        capacity: int,
        refill_rate: float,
        cache: Any = None,
        key_prefix: str = "ratelimit:tb:",
    ) -> None:
        """
        Initialize token bucket limiter.

        Args:
            capacity: Maximum tokens in bucket (burst capacity)
            refill_rate: Tokens added per second
            cache: Cache backend (uses in-memory if None)
            key_prefix: Prefix for cache keys
        """
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._cache = cache
        self._key_prefix = key_prefix
        self._local_store: dict[str, dict[str, float]] = {}
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "token_bucket"

    def _get_cache_key(self, key: str) -> str:
        return f"{self._key_prefix}{key}"

    async def _get_bucket(self, key: str, now: float | None = None) -> dict[str, float]:
        """Get bucket state from cache or local store."""
        if self._cache:
            try:
                data = await self._cache.get(self._get_cache_key(key))
                if data:
                    return data
            except Exception as e:
                logger.warning(f"Cache error in token bucket: {e}")

        if key not in self._local_store:
            # Initialize bucket with full capacity
            # Use provided timestamp for consistency with caller
            self._local_store[key] = {
                "tokens": float(self._capacity),
                "last_update": now if now is not None else time.time(),
            }

        return self._local_store[key]

    async def _set_bucket(self, key: str, bucket: dict[str, float]) -> None:
        """Store bucket state in cache or local store."""
        # Calculate TTL based on time to refill bucket
        empty_tokens = self._capacity - bucket["tokens"]
        if empty_tokens > 0 and self._refill_rate > 0:
            ttl = int(empty_tokens / self._refill_rate) + 60
        else:
            ttl = 3600

        if self._cache:
            try:
                await self._cache.set(self._get_cache_key(key), bucket, ttl_seconds=ttl)
            except Exception as e:
                logger.warning(f"Cache error in token bucket: {e}")

        self._local_store[key] = bucket

    def _refill_tokens(self, bucket: dict[str, float], now: float) -> float:
        """Calculate current token count after refilling."""
        elapsed = now - bucket["last_update"]
        tokens = bucket["tokens"] + (elapsed * self._refill_rate)
        return min(tokens, self._capacity)

    async def check(self, key: str) -> RateLimitResult:
        """Check rate limit without consuming."""
        now = time.time()
        bucket = await self._get_bucket(key, now)
        current_tokens = self._refill_tokens(bucket, now)

        allowed = current_tokens >= 1
        remaining = int(current_tokens)

        # Calculate when bucket will be full
        if current_tokens < self._capacity:
            time_to_full = (self._capacity - current_tokens) / self._refill_rate
            reset_at = datetime.utcfromtimestamp(now + time_to_full)
        else:
            reset_at = datetime.utcnow()

        retry_after = None
        if not allowed:
            retry_after = (1 - current_tokens) / self._refill_rate

        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            limit=self._capacity,
            reset_at=reset_at,
            retry_after=retry_after,
        )

    async def consume(self, key: str, tokens: int = 1) -> RateLimitResult:
        """Consume tokens from the bucket."""
        async with self._lock:
            now = time.time()
            bucket = await self._get_bucket(key, now)
            current_tokens = self._refill_tokens(bucket, now)

            if current_tokens >= tokens:
                # Consume tokens
                new_tokens = current_tokens - tokens
                await self._set_bucket(key, {"tokens": new_tokens, "last_update": now})

                return RateLimitResult(
                    allowed=True,
                    remaining=int(new_tokens),
                    limit=self._capacity,
                    reset_at=datetime.utcfromtimestamp(
                        now + (self._capacity - new_tokens) / self._refill_rate
                    ),
                    retry_after=None,
                )
            else:
                # Not enough tokens
                retry_after = (tokens - current_tokens) / self._refill_rate

                return RateLimitResult(
                    allowed=False,
                    remaining=int(current_tokens),
                    limit=self._capacity,
                    reset_at=datetime.utcfromtimestamp(now + retry_after),
                    retry_after=retry_after,
                )

    async def reset(self, key: str) -> bool:
        """Reset bucket to full capacity."""
        bucket = {"tokens": float(self._capacity), "last_update": time.time()}

        if self._cache:
            try:
                await self._cache.set(
                    self._get_cache_key(key),
                    bucket,
                    ttl_seconds=3600,
                )
            except Exception as e:
                logger.warning(f"Cache error in token bucket reset: {e}")

        self._local_store[key] = bucket
        return True
