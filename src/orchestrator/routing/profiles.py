"""Routing profiles for different use case priorities."""

from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar


class ProfileType(Enum):
    """Predefined routing profile types."""

    QUALITY = "quality"  # Best quality, cost secondary
    BALANCED = "balanced"  # Balance all factors
    SPEED = "speed"  # Lowest latency priority
    BUDGET = "budget"  # Lowest cost priority
    CUSTOM = "custom"  # User-defined weights


@dataclass
class RoutingProfile:
    """
    Configuration for model routing priorities.

    Weights should sum to 1.0 for proper score calculation.
    Each weight determines how much that factor contributes to the final score.
    """

    name: str
    """Profile name for identification."""

    quality_weight: float = 0.4
    """Weight for quality metrics (ELO, benchmarks)."""

    latency_weight: float = 0.3
    """Weight for latency metrics (p90, TTFT)."""

    cost_weight: float = 0.3
    """Weight for cost metrics ($/M tokens)."""

    context_weight: float = 0.0
    """Weight for context length (optional boost)."""

    min_quality_threshold: float = 0.0
    """Minimum normalized quality score (0.0-1.0)."""

    max_latency_ms: float | None = None
    """Maximum acceptable latency in milliseconds."""

    max_cost_per_million: float | None = None
    """Maximum acceptable cost per million tokens."""

    min_context_length: int | None = None
    """Minimum required context length."""

    description: str = ""
    """Human-readable description of the profile."""

    def __post_init__(self) -> None:
        """Validate and normalize weights."""
        total = self.quality_weight + self.latency_weight + self.cost_weight + self.context_weight
        if abs(total - 1.0) > 0.01:
            # Normalize weights to sum to 1.0
            if total > 0:
                self.quality_weight /= total
                self.latency_weight /= total
                self.cost_weight /= total
                self.context_weight /= total

    def meets_constraints(
        self,
        quality_score: float,
        latency_ms: float | None = None,
        cost_per_million: float | None = None,
        context_length: int | None = None,
    ) -> bool:
        """
        Check if a model meets this profile's hard constraints.

        Args:
            quality_score: Normalized quality score (0.0-1.0)
            latency_ms: Model latency in milliseconds
            cost_per_million: Cost per million tokens
            context_length: Model context length

        Returns:
            True if all constraints are met
        """
        if quality_score < self.min_quality_threshold:
            return False

        if self.max_latency_ms is not None and latency_ms is not None:
            if latency_ms > self.max_latency_ms:
                return False

        if self.max_cost_per_million is not None and cost_per_million is not None:
            if cost_per_million > self.max_cost_per_million:
                return False

        if self.min_context_length is not None and context_length is not None:
            if context_length < self.min_context_length:
                return False

        return True

    def calculate_score(
        self,
        quality: float,
        latency: float,
        cost: float,
        context: float = 1.0,
    ) -> float:
        """
        Calculate weighted composite score.

        Args:
            quality: Normalized quality score (0.0-1.0)
            latency: Normalized latency score (0.0-1.0)
            cost: Normalized cost score (0.0-1.0)
            context: Normalized context score (0.0-1.0)

        Returns:
            Weighted composite score (0.0-1.0)
        """
        return (
            self.quality_weight * quality
            + self.latency_weight * latency
            + self.cost_weight * cost
            + self.context_weight * context
        )


# Built-in routing profiles
QUALITY_PROFILE = RoutingProfile(
    name="quality",
    quality_weight=0.7,
    latency_weight=0.15,
    cost_weight=0.15,
    min_quality_threshold=0.6,
    description="Prioritize highest quality models, less concern for cost/speed",
)

BALANCED_PROFILE = RoutingProfile(
    name="balanced",
    quality_weight=0.4,
    latency_weight=0.3,
    cost_weight=0.3,
    description="Balance quality, speed, and cost equally",
)

SPEED_PROFILE = RoutingProfile(
    name="speed",
    quality_weight=0.2,
    latency_weight=0.6,
    cost_weight=0.2,
    max_latency_ms=1000,
    description="Prioritize fastest response times",
)

BUDGET_PROFILE = RoutingProfile(
    name="budget",
    quality_weight=0.25,
    latency_weight=0.15,
    cost_weight=0.6,
    max_cost_per_million=1.0,
    description="Prioritize lowest cost models",
)

LONG_CONTEXT_PROFILE = RoutingProfile(
    name="long_context",
    quality_weight=0.3,
    latency_weight=0.2,
    cost_weight=0.2,
    context_weight=0.3,
    min_context_length=100000,
    description="Prioritize models with large context windows",
)

# Export all built-in profiles
BUILTIN_PROFILES: dict[str, RoutingProfile] = {
    "quality": QUALITY_PROFILE,
    "balanced": BALANCED_PROFILE,
    "speed": SPEED_PROFILE,
    "budget": BUDGET_PROFILE,
    "long_context": LONG_CONTEXT_PROFILE,
}


def get_profile(name: str) -> RoutingProfile:
    """
    Get a routing profile by name.

    Args:
        name: Profile name

    Returns:
        Matching profile

    Raises:
        ValueError: If profile not found
    """
    if name in BUILTIN_PROFILES:
        return BUILTIN_PROFILES[name]
    raise ValueError(f"Unknown profile: {name}. Available: {list(BUILTIN_PROFILES.keys())}")
