"""Entity resolver for matching models across benchmark sources."""

import logging
from dataclasses import dataclass
from enum import Enum

from orchestrator.resolution.normalizer import NameNormalizer
from orchestrator.resolution.matcher import SimilarityMatcher, MatchResult

logger = logging.getLogger(__name__)


class MatchConfidence(Enum):
    """Confidence levels for entity matches."""

    EXACT = "exact"  # Score = 1.0
    HIGH = "high"  # Score >= 0.95
    MEDIUM = "medium"  # Score 0.80-0.95
    LOW = "low"  # Score < 0.80


@dataclass
class ResolvedEntity:
    """Result of entity resolution."""

    source_name: str
    """Original name from source."""

    canonical_id: int | None
    """ID of matched canonical model, or None if new."""

    canonical_name: str | None
    """Name of matched canonical model."""

    confidence: MatchConfidence
    """Confidence level of the match."""

    score: float
    """Similarity score."""

    needs_review: bool
    """Whether this match needs human review."""

    def __repr__(self) -> str:
        return (
            f"ResolvedEntity({self.source_name!r} -> "
            f"{self.canonical_name!r}, {self.confidence.value})"
        )


class EntityResolver:
    """
    Resolves model names across different benchmark sources.

    Uses normalization and fuzzy matching to link models
    from OpenRouter, LMSYS, and HuggingFace to canonical entries.
    """

    # Thresholds for confidence levels
    HIGH_CONFIDENCE_THRESHOLD = 0.95
    REVIEW_THRESHOLD = 0.80

    def __init__(
        self,
        normalizer: NameNormalizer | None = None,
        matcher: SimilarityMatcher | None = None,
        auto_link_threshold: float = 0.95,
        review_threshold: float = 0.80,
    ) -> None:
        """
        Initialize the resolver.

        Args:
            normalizer: Name normalizer instance
            matcher: Similarity matcher instance
            auto_link_threshold: Score above which to auto-link
            review_threshold: Score above which to flag for review
        """
        self._normalizer = normalizer or NameNormalizer()
        self._matcher = matcher or SimilarityMatcher()
        self._auto_link_threshold = auto_link_threshold
        self._review_threshold = review_threshold

    def resolve(
        self,
        source_name: str,
        canonical_models: dict[int, str],
    ) -> ResolvedEntity:
        """
        Resolve a source model name to a canonical model.

        Args:
            source_name: Model name from a benchmark source
            canonical_models: Dict of {model_id: model_name} for canonical models

        Returns:
            ResolvedEntity with match information
        """
        if not canonical_models:
            return ResolvedEntity(
                source_name=source_name,
                canonical_id=None,
                canonical_name=None,
                confidence=MatchConfidence.LOW,
                score=0.0,
                needs_review=False,
            )

        # Normalize the source name
        normalized_source = self._normalizer.normalize(source_name)

        # Prepare normalized canonical names for matching
        normalized_canonicals: dict[int, str] = {}
        for model_id, name in canonical_models.items():
            normalized_canonicals[model_id] = self._normalizer.normalize(name)

        # First, check for exact match (after normalization)
        for model_id, normalized_name in normalized_canonicals.items():
            if normalized_source == normalized_name:
                return ResolvedEntity(
                    source_name=source_name,
                    canonical_id=model_id,
                    canonical_name=canonical_models[model_id],
                    confidence=MatchConfidence.EXACT,
                    score=1.0,
                    needs_review=False,
                )

        # Find best fuzzy match
        best_match: MatchResult | None = None
        best_model_id: int | None = None

        for model_id, normalized_name in normalized_canonicals.items():
            result = self._matcher.match(normalized_source, normalized_name)
            if best_match is None or result.score > best_match.score:
                best_match = result
                best_model_id = model_id

        if best_match is None or best_model_id is None:
            return ResolvedEntity(
                source_name=source_name,
                canonical_id=None,
                canonical_name=None,
                confidence=MatchConfidence.LOW,
                score=0.0,
                needs_review=False,
            )

        # Determine confidence and review status
        score = best_match.score

        if score >= self._auto_link_threshold:
            confidence = MatchConfidence.HIGH
            needs_review = False
        elif score >= self._review_threshold:
            confidence = MatchConfidence.MEDIUM
            needs_review = True  # Flag for human review
        else:
            confidence = MatchConfidence.LOW
            needs_review = False  # Too low to bother reviewing

        return ResolvedEntity(
            source_name=source_name,
            canonical_id=best_model_id,
            canonical_name=canonical_models[best_model_id],
            confidence=confidence,
            score=score,
            needs_review=needs_review,
        )

    def resolve_batch(
        self,
        source_names: list[str],
        canonical_models: dict[int, str],
    ) -> list[ResolvedEntity]:
        """
        Resolve multiple source names.

        Args:
            source_names: List of model names to resolve
            canonical_models: Dict of canonical models

        Returns:
            List of resolved entities
        """
        return [
            self.resolve(name, canonical_models)
            for name in source_names
        ]

    def get_pending_reviews(
        self,
        resolved: list[ResolvedEntity],
    ) -> list[ResolvedEntity]:
        """
        Get entities that need human review.

        Args:
            resolved: List of resolved entities

        Returns:
            List of entities needing review
        """
        return [r for r in resolved if r.needs_review]

    def get_auto_linked(
        self,
        resolved: list[ResolvedEntity],
    ) -> list[ResolvedEntity]:
        """
        Get entities that were auto-linked with high confidence.

        Args:
            resolved: List of resolved entities

        Returns:
            List of high-confidence matches
        """
        return [
            r for r in resolved
            if r.confidence in (MatchConfidence.EXACT, MatchConfidence.HIGH)
        ]

    def get_unmatched(
        self,
        resolved: list[ResolvedEntity],
    ) -> list[ResolvedEntity]:
        """
        Get entities with no good match.

        Args:
            resolved: List of resolved entities

        Returns:
            List of unmatched entities (new models)
        """
        return [
            r for r in resolved
            if r.confidence == MatchConfidence.LOW and not r.needs_review
        ]
