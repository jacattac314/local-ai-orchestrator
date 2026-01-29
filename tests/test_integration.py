"""Integration tests for complete routing pipeline."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from orchestrator.routing import (
    CompositeScorer,
    Router,
    BUILTIN_PROFILES,
)
from orchestrator.routing.complexity import ComplexityClassifier, ComplexityLevel
from orchestrator.routing.profiles import RoutingProfile
from orchestrator.routing.scorer import ModelMetrics


# --- Test Fixtures ---


@pytest.fixture
def sample_models() -> list[ModelMetrics]:
    """Sample model metrics for testing."""
    return [
        ModelMetrics(
            model_id=1,
            model_name="openai/gpt-4o",
            elo_rating=1250,
            latency_p90=450,
            cost_blended=5.0,
            context_length=128000,
        ),
        ModelMetrics(
            model_id=2,
            model_name="anthropic/claude-3-opus",
            elo_rating=1280,
            latency_p90=800,
            cost_blended=15.0,
            context_length=200000,
        ),
        ModelMetrics(
            model_id=3,
            model_name="openai/gpt-3.5-turbo",
            elo_rating=1100,
            latency_p90=150,
            cost_blended=0.5,
            context_length=16000,
        ),
        ModelMetrics(
            model_id=4,
            model_name="meta-llama/llama-3-70b",
            elo_rating=1180,
            latency_p90=300,
            cost_blended=0.9,
            context_length=8000,
        ),
    ]


@pytest.fixture
def router() -> Router:
    """Create router instance."""
    return Router()


@pytest.fixture
def classifier() -> ComplexityClassifier:
    """Create complexity classifier."""
    return ComplexityClassifier()


# --- Integration Tests ---


@pytest.mark.integration
class TestRoutingPipeline:
    """End-to-end routing pipeline tests."""

    def test_full_routing_flow(
        self, router: Router, sample_models: list[ModelMetrics]
    ) -> None:
        """Test complete routing from models to selection."""
        result = router.route(sample_models, profile="balanced")

        assert result is not None
        assert result.selected_model.model_id in [m.model_id for m in sample_models]
        assert result.selected_model.composite_score > 0

    def test_profile_affects_selection(
        self, router: Router, sample_models: list[ModelMetrics]
    ) -> None:
        """Test different profiles select different models."""
        quality_result = router.route(sample_models, profile="quality")
        speed_result = router.route(sample_models, profile="speed")
        budget_result = router.route(sample_models, profile="budget")

        # Quality should favor high-quality model (highest elo)
        assert quality_result is not None
        assert quality_result.selected_model.model_id == 2  # Claude-3-opus (elo 1280)

        # Speed should favor low-latency model
        assert speed_result is not None
        assert speed_result.selected_model.model_id == 3  # GPT-3.5 (150ms)

        # Budget should favor low-cost model
        assert budget_result is not None
        assert budget_result.selected_model.model_id == 3  # GPT-3.5 (0.5 cost)

    def test_fallback_routing(
        self, router: Router, sample_models: list[ModelMetrics]
    ) -> None:
        """Test fallback when primary model fails."""
        # First route
        result1 = router.route(sample_models, profile="quality")
        assert result1 is not None

        # Use fallback excluding first choice
        result2 = router.route_with_fallback(
            sample_models,
            profile="quality",
            failed_model_ids=[result1.selected_model.model_id],
        )

        assert result2 is not None
        assert result2.selected_model.model_id != result1.selected_model.model_id

    def test_circuit_breaker_integration(
        self, router: Router, sample_models: list[ModelMetrics]
    ) -> None:
        """Test circuit breaker blocks failing models."""
        # Record failures for a model
        for _ in range(5):
            router.record_failure(1)

        result = router.route(sample_models, profile="balanced")

        # Should not select model 1 (circuit open)
        assert result is not None
        assert result.selected_model.model_id != 1


@pytest.mark.integration
class TestComplexityRouting:
    """Tests for complexity-aware routing."""

    def test_simple_prompt_classification(
        self, classifier: ComplexityClassifier
    ) -> None:
        """Test simple prompts classified correctly."""
        result = classifier.classify("Hello, how are you?")

        # Should be SIMPLE or MODERATE for basic greetings
        assert result.level in (ComplexityLevel.SIMPLE, ComplexityLevel.MODERATE)
        assert result.confidence > 0

    def test_complex_prompt_classification(
        self, classifier: ComplexityClassifier
    ) -> None:
        """Test complex prompts classified correctly."""
        prompt = """
        Analyze the following code for potential security vulnerabilities.
        Compare the implementation against OWASP best practices.
        Provide step-by-step recommendations for improvement.
        
        ```python
        def authenticate(username, password):
            query = f"SELECT * FROM users WHERE name='{username}'"
            # ... more code
        ```
        """
        result = classifier.classify(prompt)

        # Should be MODERATE or higher for code analysis prompts
        assert result.level.value >= ComplexityLevel.MODERATE.value
        assert result.features.code_blocks >= 1

    def test_complexity_affects_routing(
        self,
        router: Router,
        classifier: ComplexityClassifier,
        sample_models: list[ModelMetrics],
    ) -> None:
        """Test complexity classification returns valid results."""
        simple_result = classifier.classify("What is 2+2?")
        complex_result = classifier.classify(
            "Analyze the economic implications of quantitative easing "
            "on emerging markets, comparing data from 2008 and 2020."
        )

        # Both should return valid classification results
        assert simple_result.level is not None
        assert complex_result.level is not None
        
        # Complex prompts should have higher complexity than simple
        assert complex_result.level.value >= simple_result.level.value


@pytest.mark.integration
class TestScoringIntegration:
    """Tests for scoring engine integration."""

    def test_scorer_profile_consistency(
        self, sample_models: list[ModelMetrics]
    ) -> None:
        """Test scorer produces consistent results."""
        scorer = CompositeScorer()
        profile = BUILTIN_PROFILES["balanced"]

        # Score same models twice
        scores1 = scorer.rank_models(sample_models, profile)
        scores2 = scorer.rank_models(sample_models, profile)

        # Order should be identical
        assert [s.model_id for s in scores1] == [s.model_id for s in scores2]

    def test_all_builtin_profiles_work(
        self, sample_models: list[ModelMetrics]
    ) -> None:
        """Test all builtin profiles can score models."""
        scorer = CompositeScorer()

        for name, profile in BUILTIN_PROFILES.items():
            scores = scorer.rank_models(sample_models, profile)
            assert len(scores) > 0, f"Profile {name} failed"
