"""
Quota management service.

Provides unified quota tracking with multiple time windows,
per-user limits, and integration with the caching layer.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from orchestrator.quota.limiter import (
    RateLimiter,
    RateLimitResult,
    SlidingWindowLimiter,
)

logger = logging.getLogger(__name__)


class QuotaStatus(str, Enum):
    """Current quota status."""

    OK = "ok"
    WARNING = "warning"  # Approaching limit (>80%)
    EXCEEDED = "exceeded"
    DISABLED = "disabled"


@dataclass
class QuotaConfig:
    """
    Quota configuration for rate limiting.

    Defines limits for multiple time windows.
    Set any limit to 0 to disable that window.
    """

    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    requests_per_day: int = 10000
    warning_threshold: float = 0.8  # Warn at 80% usage
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QuotaConfig:
        return cls(
            requests_per_minute=data.get("requests_per_minute", 60),
            requests_per_hour=data.get("requests_per_hour", 1000),
            requests_per_day=data.get("requests_per_day", 10000),
            warning_threshold=data.get("warning_threshold", 0.8),
            enabled=data.get("enabled", True),
        )


@dataclass
class QuotaResult:
    """Result of a quota check."""

    allowed: bool
    """Whether the request is allowed."""

    status: QuotaStatus
    """Current quota status."""

    reason: str
    """Human-readable reason."""

    minute_remaining: int = 0
    """Remaining requests this minute."""

    hour_remaining: int = 0
    """Remaining requests this hour."""

    day_remaining: int = 0
    """Remaining requests today."""

    retry_after: float | None = None
    """Seconds to wait before retrying (if exceeded)."""

    limits: dict[str, int] = field(default_factory=dict)
    """Configured limits."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "status": self.status.value,
            "reason": self.reason,
            "remaining": {
                "minute": self.minute_remaining,
                "hour": self.hour_remaining,
                "day": self.day_remaining,
            },
            "limits": self.limits,
            "retry_after": self.retry_after,
        }


@dataclass
class QuotaManager:
    """
    Manages request quotas and rate limiting.

    Supports multiple time windows and per-user tracking.
    Integrates with cache backends for distributed deployments.
    """

    config: QuotaConfig = field(default_factory=QuotaConfig)
    config_path: str = "quota_config.json"

    _minute_limiter: RateLimiter | None = None
    _hour_limiter: RateLimiter | None = None
    _day_limiter: RateLimiter | None = None
    _cache: Any = None
    _initialized: bool = False

    def initialize(
        self,
        cache: Any = None,
        config_path: str = "quota_config.json",
    ) -> None:
        """
        Initialize quota manager with cache backend.

        Args:
            cache: Cache backend for distributed tracking
            config_path: Path to configuration file
        """
        self._cache = cache
        self.config_path = config_path
        self._load_config()
        self._setup_limiters()
        self._initialized = True

        logger.info(
            f"Quota manager initialized: "
            f"{self.config.requests_per_minute}/min, "
            f"{self.config.requests_per_hour}/hr, "
            f"{self.config.requests_per_day}/day"
        )

    def _load_config(self) -> None:
        """Load configuration from file."""
        path = Path(self.config_path)
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                self.config = QuotaConfig.from_dict(data)
                logger.info(f"Loaded quota config from {self.config_path}")
            except Exception as e:
                logger.warning(f"Failed to load quota config: {e}, using defaults")
                self.config = QuotaConfig()
        else:
            self.config = QuotaConfig()

    def save_config(self) -> None:
        """Persist configuration to file."""
        path = Path(self.config_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            json.dump(self.config.to_dict(), f, indent=2)

        logger.info(f"Saved quota config to {self.config_path}")

    def _setup_limiters(self) -> None:
        """Set up rate limiters for each time window."""
        if self.config.requests_per_minute > 0:
            self._minute_limiter = SlidingWindowLimiter(
                limit=self.config.requests_per_minute,
                window_seconds=60,
                cache=self._cache,
                key_prefix="quota:minute:",
            )

        if self.config.requests_per_hour > 0:
            self._hour_limiter = SlidingWindowLimiter(
                limit=self.config.requests_per_hour,
                window_seconds=3600,
                cache=self._cache,
                key_prefix="quota:hour:",
            )

        if self.config.requests_per_day > 0:
            self._day_limiter = SlidingWindowLimiter(
                limit=self.config.requests_per_day,
                window_seconds=86400,
                cache=self._cache,
                key_prefix="quota:day:",
            )

    def update_config(
        self,
        requests_per_minute: int | None = None,
        requests_per_hour: int | None = None,
        requests_per_day: int | None = None,
        warning_threshold: float | None = None,
        enabled: bool | None = None,
    ) -> QuotaConfig:
        """
        Update quota configuration.

        Args:
            requests_per_minute: New minute limit (0 to disable)
            requests_per_hour: New hour limit (0 to disable)
            requests_per_day: New day limit (0 to disable)
            warning_threshold: New warning threshold (0.0-1.0)
            enabled: Enable/disable quota enforcement

        Returns:
            Updated configuration
        """
        if requests_per_minute is not None:
            self.config.requests_per_minute = max(0, requests_per_minute)
        if requests_per_hour is not None:
            self.config.requests_per_hour = max(0, requests_per_hour)
        if requests_per_day is not None:
            self.config.requests_per_day = max(0, requests_per_day)
        if warning_threshold is not None:
            self.config.warning_threshold = max(0.0, min(1.0, warning_threshold))
        if enabled is not None:
            self.config.enabled = enabled

        self.save_config()
        self._setup_limiters()
        return self.config

    async def check_quota(self, identifier: str = "default") -> QuotaResult:
        """
        Check if a request is within quota limits.

        Args:
            identifier: User/API key identifier for per-user limits

        Returns:
            QuotaResult with current quota state
        """
        if not self.config.enabled:
            return QuotaResult(
                allowed=True,
                status=QuotaStatus.DISABLED,
                reason="Quota enforcement is disabled",
                minute_remaining=self.config.requests_per_minute,
                hour_remaining=self.config.requests_per_hour,
                day_remaining=self.config.requests_per_day,
                limits={
                    "minute": self.config.requests_per_minute,
                    "hour": self.config.requests_per_hour,
                    "day": self.config.requests_per_day,
                },
            )

        # Check each time window
        minute_result = None
        hour_result = None
        day_result = None

        if self._minute_limiter:
            minute_result = await self._minute_limiter.check(identifier)
        if self._hour_limiter:
            hour_result = await self._hour_limiter.check(identifier)
        if self._day_limiter:
            day_result = await self._day_limiter.check(identifier)

        return self._build_result(minute_result, hour_result, day_result)

    async def consume_quota(self, identifier: str = "default") -> QuotaResult:
        """
        Consume quota for a request.

        Args:
            identifier: User/API key identifier for per-user limits

        Returns:
            QuotaResult after consuming quota
        """
        if not self.config.enabled:
            return await self.check_quota(identifier)

        # Consume from each time window
        minute_result = None
        hour_result = None
        day_result = None

        # First check all limits without consuming
        if self._minute_limiter:
            minute_result = await self._minute_limiter.check(identifier)
            if not minute_result.allowed:
                return self._build_result(minute_result, hour_result, day_result)

        if self._hour_limiter:
            hour_result = await self._hour_limiter.check(identifier)
            if not hour_result.allowed:
                return self._build_result(minute_result, hour_result, day_result)

        if self._day_limiter:
            day_result = await self._day_limiter.check(identifier)
            if not day_result.allowed:
                return self._build_result(minute_result, hour_result, day_result)

        # All limits passed, consume from each
        if self._minute_limiter:
            minute_result = await self._minute_limiter.consume(identifier)
        if self._hour_limiter:
            hour_result = await self._hour_limiter.consume(identifier)
        if self._day_limiter:
            day_result = await self._day_limiter.consume(identifier)

        return self._build_result(minute_result, hour_result, day_result)

    def _build_result(
        self,
        minute_result: RateLimitResult | None,
        hour_result: RateLimitResult | None,
        day_result: RateLimitResult | None,
    ) -> QuotaResult:
        """Build unified quota result from individual limiter results."""
        # Determine overall status
        allowed = True
        status = QuotaStatus.OK
        reason = "Within quota limits"
        retry_after = None
        exceeded_windows = []

        # Check minute limit
        minute_remaining = self.config.requests_per_minute
        if minute_result:
            minute_remaining = minute_result.remaining
            if not minute_result.allowed:
                allowed = False
                exceeded_windows.append("minute")
                if minute_result.retry_after:
                    retry_after = minute_result.retry_after
            elif self._is_warning(minute_result.remaining, minute_result.limit):
                status = QuotaStatus.WARNING

        # Check hour limit
        hour_remaining = self.config.requests_per_hour
        if hour_result:
            hour_remaining = hour_result.remaining
            if not hour_result.allowed:
                allowed = False
                exceeded_windows.append("hour")
                if hour_result.retry_after and (
                    retry_after is None or hour_result.retry_after > retry_after
                ):
                    retry_after = hour_result.retry_after
            elif self._is_warning(hour_result.remaining, hour_result.limit):
                status = QuotaStatus.WARNING

        # Check day limit
        day_remaining = self.config.requests_per_day
        if day_result:
            day_remaining = day_result.remaining
            if not day_result.allowed:
                allowed = False
                exceeded_windows.append("day")
                if day_result.retry_after and (
                    retry_after is None or day_result.retry_after > retry_after
                ):
                    retry_after = day_result.retry_after
            elif self._is_warning(day_result.remaining, day_result.limit):
                status = QuotaStatus.WARNING

        # Build reason message
        if not allowed:
            status = QuotaStatus.EXCEEDED
            reason = f"Quota exceeded for: {', '.join(exceeded_windows)}"
        elif status == QuotaStatus.WARNING:
            reason = "Approaching quota limits"

        return QuotaResult(
            allowed=allowed,
            status=status,
            reason=reason,
            minute_remaining=minute_remaining,
            hour_remaining=hour_remaining,
            day_remaining=day_remaining,
            retry_after=retry_after,
            limits={
                "minute": self.config.requests_per_minute,
                "hour": self.config.requests_per_hour,
                "day": self.config.requests_per_day,
            },
        )

    def _is_warning(self, remaining: int, limit: int) -> bool:
        """Check if remaining quota is below warning threshold."""
        if limit == 0:
            return False
        used_percent = 1 - (remaining / limit)
        return used_percent >= self.config.warning_threshold

    async def reset_quota(self, identifier: str = "default") -> bool:
        """
        Reset quota for an identifier.

        Args:
            identifier: User/API key identifier

        Returns:
            True if reset successful
        """
        success = True

        if self._minute_limiter:
            success = success and await self._minute_limiter.reset(identifier)
        if self._hour_limiter:
            success = success and await self._hour_limiter.reset(identifier)
        if self._day_limiter:
            success = success and await self._day_limiter.reset(identifier)

        logger.info(f"Reset quota for {identifier}")
        return success

    async def get_quota_status(self, identifier: str = "default") -> dict[str, Any]:
        """
        Get complete quota status for API response.

        Args:
            identifier: User/API key identifier

        Returns:
            Dict with quota configuration and current usage
        """
        result = await self.check_quota(identifier)

        return {
            "identifier": identifier,
            "config": self.config.to_dict(),
            "usage": result.to_dict(),
            "enabled": self.config.enabled,
        }


# Global default instance
default_quota_manager = QuotaManager()
