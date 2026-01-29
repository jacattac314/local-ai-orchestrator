"""Metric normalizers for routing score calculation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any
import math


class NormalizationMethod(Enum):
    """Methods for normalizing metric values."""

    MIN_MAX = "min_max"  # Linear scaling to [0, 1]
    Z_SCORE = "z_score"  # Standard deviation normalization
    LOG = "log"  # Logarithmic scaling
    INVERSE = "inverse"  # 1/x for "lower is better" metrics
    PERCENTILE = "percentile"  # Rank-based normalization


@dataclass
class NormalizedValue:
    """Result of metric normalization."""

    raw_value: float
    """Original value before normalization."""

    normalized_value: float
    """Normalized value in [0, 1] range (higher is better)."""

    method: NormalizationMethod
    """Method used for normalization."""

    metadata: dict[str, Any] | None = None
    """Additional context about normalization."""


class MetricNormalizer(ABC):
    """Abstract base class for metric normalizers."""

    @property
    @abstractmethod
    def metric_type(self) -> str:
        """Type of metric this normalizer handles."""
        ...

    @property
    @abstractmethod
    def higher_is_better(self) -> bool:
        """Whether higher raw values are better."""
        ...

    @abstractmethod
    def normalize(self, value: float, context: dict[str, Any] | None = None) -> NormalizedValue:
        """
        Normalize a metric value to [0, 1] range.

        Args:
            value: Raw metric value
            context: Optional context (e.g., distribution stats)

        Returns:
            NormalizedValue with result
        """
        ...

    def normalize_batch(
        self, 
        values: list[float], 
        context: dict[str, Any] | None = None
    ) -> list[NormalizedValue]:
        """Normalize a batch of values."""
        return [self.normalize(v, context) for v in values]


class QualityNormalizer(MetricNormalizer):
    """
    Normalizer for quality metrics (ELO, benchmark scores).

    Quality metrics are typically "higher is better" and benefit
    from min-max normalization within the observed range.
    """

    # Reference ranges for different quality metrics
    METRIC_RANGES: dict[str, tuple[float, float]] = {
        "elo_rating": (800, 1400),  # LMSYS Arena typical range
        "benchmark_mmlu_pro": (0, 100),
        "benchmark_ifeval": (0, 100),
        "benchmark_bbh": (0, 100),
        "benchmark_gpqa": (0, 100),
        "benchmark_math": (0, 100),
        "benchmark_average": (0, 100),
    }

    def __init__(
        self,
        metric_name: str = "elo_rating",
        floor: float | None = None,
        ceiling: float | None = None,
    ) -> None:
        """
        Initialize quality normalizer.

        Args:
            metric_name: Name of the quality metric
            floor: Minimum value (uses default if None)
            ceiling: Maximum value (uses default if None)
        """
        self._metric_name = metric_name
        
        default_range = self.METRIC_RANGES.get(metric_name, (0, 100))
        self._floor = floor if floor is not None else default_range[0]
        self._ceiling = ceiling if ceiling is not None else default_range[1]

    @property
    def metric_type(self) -> str:
        return self._metric_name

    @property
    def higher_is_better(self) -> bool:
        return True

    def normalize(self, value: float, context: dict[str, Any] | None = None) -> NormalizedValue:
        """
        Normalize quality metric using min-max scaling.

        Higher quality scores map to higher normalized values.
        """
        # Use context-provided range if available
        ctx = context or {}
        floor = ctx.get("floor", self._floor)
        ceiling = ctx.get("ceiling", self._ceiling)

        # Clamp and normalize
        clamped = max(floor, min(ceiling, value))
        range_size = ceiling - floor

        if range_size == 0:
            normalized = 0.5  # Avoid division by zero
        else:
            normalized = (clamped - floor) / range_size

        return NormalizedValue(
            raw_value=value,
            normalized_value=normalized,
            method=NormalizationMethod.MIN_MAX,
            metadata={"floor": floor, "ceiling": ceiling},
        )


class LatencyNormalizer(MetricNormalizer):
    """
    Normalizer for latency metrics (p90, TTFT).

    Latency is "lower is better", so we invert the normalized value.
    Uses log scaling to handle wide latency ranges gracefully.
    """

    # Target latency ranges in milliseconds
    EXCELLENT_MS = 100  # < 100ms is excellent
    ACCEPTABLE_MS = 1000  # < 1s is acceptable
    POOR_MS = 5000  # > 5s is poor

    def __init__(
        self,
        metric_name: str = "latency_p90",
        excellent_threshold: float = 100,
        poor_threshold: float = 5000,
    ) -> None:
        """
        Initialize latency normalizer.

        Args:
            metric_name: Name of the latency metric
            excellent_threshold: Latency below this is excellent (ms)
            poor_threshold: Latency above this is poor (ms)
        """
        self._metric_name = metric_name
        self._excellent = excellent_threshold
        self._poor = poor_threshold

    @property
    def metric_type(self) -> str:
        return self._metric_name

    @property
    def higher_is_better(self) -> bool:
        return False  # Lower latency is better

    def normalize(self, value: float, context: dict[str, Any] | None = None) -> NormalizedValue:
        """
        Normalize latency using log scaling with inversion.

        Lower latency maps to higher normalized values.
        """
        ctx = context or {}
        excellent = ctx.get("excellent_threshold", self._excellent)
        poor = ctx.get("poor_threshold", self._poor)

        if value <= 0:
            # Invalid latency, assume excellent
            normalized = 1.0
        elif value <= excellent:
            # Excellent latency
            normalized = 1.0
        elif value >= poor:
            # Poor latency
            normalized = 0.0
        else:
            # Log scale between excellent and poor
            # Map log(excellent) to 1.0 and log(poor) to 0.0
            log_value = math.log(value)
            log_excellent = math.log(excellent)
            log_poor = math.log(poor)
            
            normalized = 1.0 - (log_value - log_excellent) / (log_poor - log_excellent)

        return NormalizedValue(
            raw_value=value,
            normalized_value=max(0.0, min(1.0, normalized)),
            method=NormalizationMethod.LOG,
            metadata={"excellent": excellent, "poor": poor},
        )


class CostNormalizer(MetricNormalizer):
    """
    Normalizer for cost metrics (price per million tokens).

    Cost is "lower is better", using inverse log scaling.
    """

    # Cost ranges in dollars per million tokens
    FREE_THRESHOLD = 0.001  # Effectively free
    CHEAP_THRESHOLD = 0.5  # Budget-friendly
    EXPENSIVE_THRESHOLD = 50.0  # Premium pricing

    def __init__(
        self,
        metric_name: str = "cost_blended",
        cheap_threshold: float = 0.5,
        expensive_threshold: float = 50.0,
    ) -> None:
        """
        Initialize cost normalizer.

        Args:
            metric_name: Name of the cost metric
            cheap_threshold: Cost below this is cheap ($/M tokens)
            expensive_threshold: Cost above this is expensive ($/M tokens)
        """
        self._metric_name = metric_name
        self._cheap = cheap_threshold
        self._expensive = expensive_threshold

    @property
    def metric_type(self) -> str:
        return self._metric_name

    @property
    def higher_is_better(self) -> bool:
        return False  # Lower cost is better

    def normalize(self, value: float, context: dict[str, Any] | None = None) -> NormalizedValue:
        """
        Normalize cost using log scaling with inversion.

        Lower cost maps to higher normalized values.
        """
        ctx = context or {}
        cheap = ctx.get("cheap_threshold", self._cheap)
        expensive = ctx.get("expensive_threshold", self._expensive)

        if value <= 0:
            # Free model
            normalized = 1.0
        elif value <= cheap:
            # Cheap models get high scores
            # Linear interpolation from 1.0 at 0 to 0.8 at cheap threshold
            normalized = 1.0 - (value / cheap) * 0.2
        elif value >= expensive:
            # Expensive models
            normalized = 0.0
        else:
            # Log scale between cheap and expensive
            log_value = math.log(value)
            log_cheap = math.log(cheap)
            log_expensive = math.log(expensive)
            
            # Map log_cheap to 0.8 and log_expensive to 0.0
            normalized = 0.8 * (1.0 - (log_value - log_cheap) / (log_expensive - log_cheap))

        return NormalizedValue(
            raw_value=value,
            normalized_value=max(0.0, min(1.0, normalized)),
            method=NormalizationMethod.LOG,
            metadata={"cheap": cheap, "expensive": expensive},
        )


class ContextLengthNormalizer(MetricNormalizer):
    """
    Normalizer for context length (tokens).

    Larger context is generally better, using log scaling.
    """

    def __init__(self, min_context: int = 4096, max_context: int = 1000000) -> None:
        """
        Initialize context length normalizer.

        Args:
            min_context: Minimum useful context length
            max_context: Maximum expected context length
        """
        self._min = min_context
        self._max = max_context

    @property
    def metric_type(self) -> str:
        return "context_length"

    @property
    def higher_is_better(self) -> bool:
        return True

    def normalize(self, value: float, context: dict[str, Any] | None = None) -> NormalizedValue:
        """Normalize context length using log scaling."""
        if value <= 0:
            normalized = 0.0
        elif value <= self._min:
            normalized = 0.1  # Very short context
        elif value >= self._max:
            normalized = 1.0
        else:
            # Log scale
            log_value = math.log(value)
            log_min = math.log(self._min)
            log_max = math.log(self._max)
            
            normalized = 0.1 + 0.9 * (log_value - log_min) / (log_max - log_min)

        return NormalizedValue(
            raw_value=value,
            normalized_value=max(0.0, min(1.0, normalized)),
            method=NormalizationMethod.LOG,
            metadata={"min": self._min, "max": self._max},
        )
