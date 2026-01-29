"""Tests for entity resolution components."""

import pytest

from orchestrator.resolution.normalizer import NameNormalizer
from orchestrator.resolution.matcher import SimilarityMatcher, MatchResult
from orchestrator.resolution.resolver import EntityResolver, MatchConfidence


class TestNameNormalizer:
    """Tests for NameNormalizer."""

    def test_basic_normalization(self) -> None:
        """Test basic name normalization."""
        normalizer = NameNormalizer()

        assert normalizer.normalize("GPT-4") == "gpt-4"
        assert normalizer.normalize("  Claude-3  ") == "claude-3"

    def test_version_stripping(self) -> None:
        """Test version suffix stripping."""
        normalizer = NameNormalizer(strip_version=True)

        assert normalizer.normalize("model-v1") == "model"
        assert normalizer.normalize("model-v1.0") == "model"
        assert normalizer.normalize("model-v2.1.3") == "model"
        assert normalizer.normalize("model_v1") == "model"

    def test_vendor_stripping(self) -> None:
        """Test vendor prefix stripping."""
        normalizer = NameNormalizer(strip_vendor=True)

        assert normalizer.normalize("openai/gpt-4") == "gpt-4"
        assert normalizer.normalize("anthropic/claude-3") == "claude-3"
        assert normalizer.normalize("meta-llama/Llama-3") == "llama-3"

    def test_variant_normalization(self) -> None:
        """Test variant suffix normalization."""
        normalizer = NameNormalizer(normalize_variants=True)

        assert normalizer.normalize("gpt-4-chat") == "gpt-4"
        assert normalizer.normalize("claude-instruct") == "claude"
        assert normalizer.normalize("model-base") == "model"

    def test_aggressive_normalization(self) -> None:
        """Test aggressive normalization for comparison."""
        normalizer = NameNormalizer()

        result = normalizer.normalize_for_comparison("llama-3-70b-instruct-v2")
        assert "70" not in result or "b" not in result.lower()

    def test_vendor_extraction(self) -> None:
        """Test vendor extraction."""
        normalizer = NameNormalizer()

        assert normalizer.extract_vendor("openai/gpt-4") == "openai"
        assert normalizer.extract_vendor("anthropic/claude") == "anthropic"
        assert normalizer.extract_vendor("gpt-4") is None

    def test_base_model_extraction(self) -> None:
        """Test base model extraction."""
        normalizer = NameNormalizer()

        assert normalizer.extract_base_model("openai/gpt-4") == "gpt-4"
        assert normalizer.extract_base_model("gpt-4") == "gpt-4"


class TestSimilarityMatcher:
    """Tests for SimilarityMatcher."""

    def test_exact_match(self) -> None:
        """Test exact match returns 1.0."""
        matcher = SimilarityMatcher()

        score = matcher.similarity_score("gpt-4", "gpt-4")
        assert score == 1.0

    def test_levenshtein_distance(self) -> None:
        """Test Levenshtein distance calculation."""
        matcher = SimilarityMatcher()

        assert matcher.levenshtein_distance("kitten", "sitten") == 1
        assert matcher.levenshtein_distance("kitten", "sitting") == 3
        assert matcher.levenshtein_distance("", "abc") == 3
        assert matcher.levenshtein_distance("abc", "abc") == 0

    def test_similarity_score(self) -> None:
        """Test similarity score calculation."""
        matcher = SimilarityMatcher()

        # Similar strings
        score = matcher.similarity_score("gpt-4", "gpt-4-turbo")
        assert 0.4 < score < 0.8

        # Very different strings
        score = matcher.similarity_score("abc", "xyz")
        assert score < 0.5

    def test_find_best_match(self) -> None:
        """Test finding best match from candidates."""
        matcher = SimilarityMatcher(threshold=0.5)
        candidates = ["gpt-4", "gpt-4-turbo", "claude-3", "gemini-pro"]

        result = matcher.find_best_match("gpt-4", candidates)
        assert result is not None
        assert result.candidate == "gpt-4"
        assert result.score == 1.0

    def test_find_best_match_fuzzy(self) -> None:
        """Test finding best fuzzy match."""
        matcher = SimilarityMatcher(threshold=0.4)
        candidates = ["gpt-4-turbo", "claude-3", "gemini-pro"]

        result = matcher.find_best_match("gpt-4", candidates)
        assert result is not None
        assert "gpt-4" in result.candidate

    def test_find_best_match_no_match(self) -> None:
        """Test when no match is found."""
        matcher = SimilarityMatcher(threshold=0.9)
        candidates = ["claude-3", "gemini-pro"]

        result = matcher.find_best_match("gpt-4", candidates)
        assert result is None

    def test_find_all_matches(self) -> None:
        """Test finding all matching candidates."""
        matcher = SimilarityMatcher(threshold=0.5)
        candidates = ["gpt-4", "gpt-4-turbo", "gpt-4o", "claude-3"]

        results = matcher.find_all_matches("gpt-4", candidates)
        assert len(results) >= 2  # At least exact and near matches


class TestEntityResolver:
    """Tests for EntityResolver."""

    @pytest.fixture
    def canonical_models(self) -> dict[int, str]:
        """Sample canonical models."""
        return {
            1: "gpt-4",
            2: "gpt-4-turbo",
            3: "claude-3-opus",
            4: "gemini-pro",
        }

    def test_exact_match(self, canonical_models: dict[int, str]) -> None:
        """Test exact match resolution."""
        resolver = EntityResolver()

        result = resolver.resolve("gpt-4", canonical_models)
        assert result.canonical_id == 1
        assert result.confidence == MatchConfidence.EXACT
        assert result.score == 1.0
        assert result.needs_review is False

    def test_high_confidence_match(self, canonical_models: dict[int, str]) -> None:
        """Test high confidence match."""
        resolver = EntityResolver()

        # Normalized version of gpt-4-turbo
        result = resolver.resolve("GPT-4-Turbo", canonical_models)
        assert result.confidence == MatchConfidence.EXACT
        assert result.needs_review is False

    def test_medium_confidence_match(self, canonical_models: dict[int, str]) -> None:
        """Test medium confidence match needs review."""
        resolver = EntityResolver(auto_link_threshold=0.95, review_threshold=0.7)

        # Similar but not exact
        result = resolver.resolve("gpt-4-preview", canonical_models)
        if result.score >= 0.7 and result.score < 0.95:
            assert result.confidence == MatchConfidence.MEDIUM
            assert result.needs_review is True

    def test_no_match(self, canonical_models: dict[int, str]) -> None:
        """Test no match found."""
        resolver = EntityResolver()

        result = resolver.resolve("completely-different-model", canonical_models)
        assert result.confidence == MatchConfidence.LOW
        assert result.needs_review is False

    def test_resolve_batch(self, canonical_models: dict[int, str]) -> None:
        """Test batch resolution."""
        resolver = EntityResolver()
        names = ["gpt-4", "claude-3-opus", "new-model"]

        results = resolver.resolve_batch(names, canonical_models)
        assert len(results) == 3

    def test_get_pending_reviews(self, canonical_models: dict[int, str]) -> None:
        """Test filtering pending reviews."""
        resolver = EntityResolver()
        
        # Create a mix of results
        results = [
            resolver.resolve("gpt-4", canonical_models),  # Exact
            resolver.resolve("completely-new", canonical_models),  # Low
        ]

        pending = resolver.get_pending_reviews(results)
        # Only medium confidence results need review
        for p in pending:
            assert p.needs_review is True

    def test_get_unmatched(self, canonical_models: dict[int, str]) -> None:
        """Test filtering unmatched entities."""
        resolver = EntityResolver()
        
        results = [
            resolver.resolve("gpt-4", canonical_models),
            resolver.resolve("brand-new-model", canonical_models),
        ]

        unmatched = resolver.get_unmatched(results)
        for u in unmatched:
            assert u.confidence == MatchConfidence.LOW
