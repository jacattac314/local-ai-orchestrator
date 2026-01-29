"""Composite scorer for model ranking."""

import logging
from dataclasses import dataclass, field
from typing import Any

from orchestrator.routing.normalizers import (
    QualityNormalizer,
    LatencyNormalizer,
    CostNormalizer,
    ContextLengthNormalizer,
    NormalizedValue,
)
from orchestrator.routing.profiles import RoutingProfile

logger = logging.getLogger(__name__)


@dataclass
class ModelScore:
    """Complete scoring result for a model."""

    model_id: int
    """Database ID of the model."""

    model_name: str
    """Model name for display."""

    composite_score: float
    """Final weighted score (0.0-1.0)."""

    quality_score: float
    """Normalized quality score."""

    latency_score: float
    """Normalized latency score."""

    cost_score: float
    """Normalized cost score."""

    context_score: float = 1.0
    """Normalized context score."""

    meets_constraints: bool = True
    """Whether model meets profile constraints."""

    raw_metrics: dict[str, float] = field(default_factory=dict)
    """Original metric values before normalization."""

    def __lt__(self, other: "ModelScore") -> bool:
        """Compare by composite score for sorting."""
        return self.composite_score < other.composite_score


@dataclass
class ModelMetrics:
    """Raw metrics for a model."""

    model_id: int
    model_name: str
    
    # Quality metrics (pick best available)
    elo_rating: float | None = None
    benchmark_average: float | None = None
    
    # Latency metrics
    latency_p90: float | None = None
    ttft_p90: float | None = None
    
    # Cost metrics
    cost_prompt: float | None = None
    cost_completion: float | None = None
    cost_blended: float | None = None
    
    # Other
    context_length: int | None = None


class CompositeScorer:
    """
    Calculates composite scores for models based on routing profiles.

    Aggregates normalized metrics and applies profile weights.
    """

    def __init__(self) -> None:
        """Initialize the scorer with default normalizers."""
        self._quality_elo = QualityNormalizer("elo_rating")
        self._quality_bench = QualityNormalizer("benchmark_average")
        self._latency = LatencyNormalizer()
        self._cost = CostNormalizer()
        self._context = ContextLengthNormalizer()

    def score_model(
        self,
        metrics: ModelMetrics,
        profile: RoutingProfile,
    ) -> ModelScore:
        """
        Calculate composite score for a single model.

        Args:
            metrics: Raw metrics for the model
            profile: Routing profile with weights

        Returns:
            ModelScore with normalized and composite scores
        """
        # Calculate quality score (prefer ELO, fallback to benchmark average)
        quality_score = 0.5  # Default if no quality data
        if metrics.elo_rating is not None:
            quality_score = self._quality_elo.normalize(metrics.elo_rating).normalized_value
        elif metrics.benchmark_average is not None:
            quality_score = self._quality_bench.normalize(metrics.benchmark_average).normalized_value

        # Calculate latency score
        latency_score = 0.5  # Default if no latency data
        if metrics.latency_p90 is not None:
            latency_score = self._latency.normalize(metrics.latency_p90).normalized_value
        elif metrics.ttft_p90 is not None:
            # TTFT is typically faster than full latency
            latency_score = self._latency.normalize(metrics.ttft_p90).normalized_value

        # Calculate cost score
        cost_score = 0.5  # Default if no cost data
        if metrics.cost_blended is not None:
            cost_score = self._cost.normalize(metrics.cost_blended).normalized_value
        elif metrics.cost_prompt is not None and metrics.cost_completion is not None:
            # Calculate blended cost if not provided
            blended = metrics.cost_prompt * 0.3 + metrics.cost_completion * 0.7
            cost_score = self._cost.normalize(blended).normalized_value

        # Calculate context score
        context_score = 1.0  # Default to max if no context data
        if metrics.context_length is not None:
            context_score = self._context.normalize(float(metrics.context_length)).normalized_value

        # Check constraints
        meets_constraints = profile.meets_constraints(
            quality_score=quality_score,
            latency_ms=metrics.latency_p90,
            cost_per_million=metrics.cost_blended,
            context_length=metrics.context_length,
        )

        # Calculate composite score
        composite = profile.calculate_score(
            quality=quality_score,
            latency=latency_score,
            cost=cost_score,
            context=context_score,
        )

        # Penalize models that don't meet constraints
        if not meets_constraints:
            composite *= 0.1  # Heavy penalty but don't exclude entirely

        return ModelScore(
            model_id=metrics.model_id,
            model_name=metrics.model_name,
            composite_score=composite,
            quality_score=quality_score,
            latency_score=latency_score,
            cost_score=cost_score,
            context_score=context_score,
            meets_constraints=meets_constraints,
            raw_metrics={
                "elo_rating": metrics.elo_rating,
                "benchmark_average": metrics.benchmark_average,
                "latency_p90": metrics.latency_p90,
                "cost_blended": metrics.cost_blended,
                "context_length": metrics.context_length,
            },
        )

    def score_models(
        self,
        models: list[ModelMetrics],
        profile: RoutingProfile,
    ) -> list[ModelScore]:
        """
        Score multiple models and return sorted by composite score.

        Args:
            models: List of model metrics
            profile: Routing profile to use

        Returns:
            List of ModelScores sorted by composite score (highest first)
        """
        scores = [self.score_model(m, profile) for m in models]
        scores.sort(reverse=True)  # Highest first
        return scores

    def rank_models(
        self,
        models: list[ModelMetrics],
        profile: RoutingProfile,
        limit: int | None = None,
        only_meeting_constraints: bool = False,
    ) -> list[ModelScore]:
        """
        Rank models and return top N.

        Args:
            models: List of model metrics
            profile: Routing profile to use
            limit: Maximum number of results
            only_meeting_constraints: Only include models meeting constraints

        Returns:
            Ranked list of ModelScores
        """
        scores = self.score_models(models, profile)

        if only_meeting_constraints:
            scores = [s for s in scores if s.meets_constraints]

        if limit:
            scores = scores[:limit]

        return scores

    def get_best_model(
        self,
        models: list[ModelMetrics],
        profile: RoutingProfile,
    ) -> ModelScore | None:
        """
        Get the best model for a profile.

        Args:
            models: List of model metrics
            profile: Routing profile to use

        Returns:
            Best scoring model or None if no models
        """
        ranked = self.rank_models(models, profile, limit=1, only_meeting_constraints=True)
        
        if ranked:
            return ranked[0]
        
        # Fallback: return best overall if none meet constraints
        all_ranked = self.rank_models(models, profile, limit=1)
        return all_ranked[0] if all_ranked else None
