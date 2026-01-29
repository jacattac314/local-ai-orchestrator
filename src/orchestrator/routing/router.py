"""Main router for model selection with fallback handling."""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

from orchestrator.routing.profiles import RoutingProfile, BUILTIN_PROFILES
from orchestrator.routing.scorer import CompositeScorer, ModelMetrics, ModelScore

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for model failure handling.

    Tracks failures and temporarily disables models that are failing.
    """

    failure_threshold: int = 3
    """Number of failures before opening circuit."""

    recovery_timeout: float = 60.0
    """Seconds to wait before testing recovery."""

    # Internal state
    _failure_count: int = 0
    _state: CircuitState = CircuitState.CLOSED
    _last_failure_time: datetime | None = None

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        if self._state == CircuitState.OPEN:
            # Check if we should try recovery
            if self._last_failure_time:
                elapsed = (datetime.utcnow() - self._last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
        return self._state

    def is_available(self) -> bool:
        """Check if the circuit allows requests."""
        return self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self) -> None:
        """Record a successful request."""
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record a failed request."""
        self._failure_count += 1
        self._last_failure_time = datetime.utcnow()

        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(f"Circuit breaker opened after {self._failure_count} failures")

    def reset(self) -> None:
        """Reset the circuit breaker."""
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._last_failure_time = None


@dataclass
class RoutingResult:
    """Result of a routing decision."""

    selected_model: ModelScore
    """The selected model to use."""

    fallback_models: list[ModelScore] = field(default_factory=list)
    """Backup models if primary fails."""

    profile_used: str = "balanced"
    """Name of the routing profile used."""

    routing_time_ms: float = 0.0
    """Time taken to make routing decision."""

    was_fallback: bool = False
    """Whether this was a fallback selection."""


class Router:
    """
    Main router for selecting AI models.

    Combines scoring, fallback handling, and circuit breaking.
    """

    def __init__(
        self,
        scorer: CompositeScorer | None = None,
        default_profile: str = "balanced",
        fallback_count: int = 2,
    ) -> None:
        """
        Initialize the router.

        Args:
            scorer: Composite scorer instance
            default_profile: Default routing profile name
            fallback_count: Number of fallback models to prepare
        """
        self._scorer = scorer or CompositeScorer()
        self._default_profile = default_profile
        self._fallback_count = fallback_count
        
        # Circuit breakers per model
        self._circuit_breakers: dict[int, CircuitBreaker] = {}

    def _get_circuit_breaker(self, model_id: int) -> CircuitBreaker:
        """Get or create circuit breaker for a model."""
        if model_id not in self._circuit_breakers:
            self._circuit_breakers[model_id] = CircuitBreaker()
        return self._circuit_breakers[model_id]

    def route(
        self,
        models: list[ModelMetrics],
        profile: RoutingProfile | str | None = None,
    ) -> RoutingResult | None:
        """
        Select the best model for a request.

        Args:
            models: Available models with metrics
            profile: Routing profile (name or instance)

        Returns:
            RoutingResult or None if no suitable model
        """
        start_time = time.perf_counter()

        # Resolve profile
        if profile is None:
            profile = BUILTIN_PROFILES.get(self._default_profile)
        elif isinstance(profile, str):
            profile = BUILTIN_PROFILES.get(profile)
        
        if profile is None:
            profile = BUILTIN_PROFILES["balanced"]

        # Filter out models with open circuit breakers
        available_models = [
            m for m in models
            if self._get_circuit_breaker(m.model_id).is_available()
        ]

        if not available_models:
            # All circuits open, try to recover with any model
            logger.warning("All circuit breakers open, allowing all models")
            available_models = models

        if not available_models:
            return None

        # Score and rank models
        ranked = self._scorer.rank_models(
            available_models,
            profile,
            limit=self._fallback_count + 1,
        )

        if not ranked:
            return None

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return RoutingResult(
            selected_model=ranked[0],
            fallback_models=ranked[1:] if len(ranked) > 1 else [],
            profile_used=profile.name,
            routing_time_ms=elapsed_ms,
            was_fallback=False,
        )

    def route_with_fallback(
        self,
        models: list[ModelMetrics],
        profile: RoutingProfile | str | None = None,
        failed_model_ids: list[int] | None = None,
    ) -> RoutingResult | None:
        """
        Select a model, excluding previously failed models.

        Args:
            models: Available models with metrics
            profile: Routing profile
            failed_model_ids: Models that have already failed

        Returns:
            RoutingResult with fallback model
        """
        failed_ids = set(failed_model_ids or [])
        
        # Filter out failed models
        available = [m for m in models if m.model_id not in failed_ids]
        
        if not available:
            return None

        result = self.route(available, profile)
        
        if result:
            result.was_fallback = len(failed_ids) > 0

        return result

    def record_success(self, model_id: int) -> None:
        """Record a successful model call."""
        self._get_circuit_breaker(model_id).record_success()

    def record_failure(self, model_id: int) -> None:
        """Record a failed model call."""
        self._get_circuit_breaker(model_id).record_failure()

    def get_model_status(self, model_id: int) -> dict[str, Any]:
        """Get the current status of a model's circuit breaker."""
        cb = self._get_circuit_breaker(model_id)
        return {
            "model_id": model_id,
            "state": cb.state.value,
            "is_available": cb.is_available(),
            "failure_count": cb._failure_count,
        }

    def reset_circuit_breaker(self, model_id: int) -> None:
        """Manually reset a model's circuit breaker."""
        self._get_circuit_breaker(model_id).reset()

    def reset_all_circuit_breakers(self) -> None:
        """Reset all circuit breakers."""
        for cb in self._circuit_breakers.values():
            cb.reset()
