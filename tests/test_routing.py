"""Tests for routing normalizers, profiles, scorer, and router."""

import pytest
from orchestrator.routing.normalizers import (
    QualityNormalizer,
    LatencyNormalizer,
    CostNormalizer,
    ContextLengthNormalizer,
    NormalizationMethod,
)
from orchestrator.routing.profiles import (
    RoutingProfile,
    BUILTIN_PROFILES,
    get_profile,
)
from orchestrator.routing.scorer import CompositeScorer, ModelMetrics, ModelScore
from orchestrator.routing.router import Router, CircuitBreaker, CircuitState


class TestQualityNormalizer:
    """Tests for QualityNormalizer."""

    def test_elo_normalization(self) -> None:
        """Test ELO rating normalization."""
        norm = QualityNormalizer("elo_rating")
        
        result = norm.normalize(1100)  # Middle of 800-1400 range
        assert 0.4 < result.normalized_value < 0.6
        assert result.method == NormalizationMethod.MIN_MAX

    def test_elo_ceiling(self) -> None:
        """Test ELO at ceiling."""
        norm = QualityNormalizer("elo_rating")
        
        result = norm.normalize(1400)
        assert result.normalized_value == 1.0

    def test_elo_floor(self) -> None:
        """Test ELO at floor."""
        norm = QualityNormalizer("elo_rating")
        
        result = norm.normalize(800)
        assert result.normalized_value == 0.0

    def test_benchmark_normalization(self) -> None:
        """Test benchmark score normalization."""
        norm = QualityNormalizer("benchmark_average")
        
        result = norm.normalize(75)
        assert result.normalized_value == 0.75


class TestLatencyNormalizer:
    """Tests for LatencyNormalizer."""

    def test_excellent_latency(self) -> None:
        """Test excellent latency scores 1.0."""
        norm = LatencyNormalizer()
        
        result = norm.normalize(50)  # 50ms is excellent
        assert result.normalized_value == 1.0

    def test_poor_latency(self) -> None:
        """Test poor latency scores 0.0."""
        norm = LatencyNormalizer()
        
        result = norm.normalize(6000)  # 6s is poor
        assert result.normalized_value == 0.0

    def test_mid_latency(self) -> None:
        """Test mid-range latency."""
        norm = LatencyNormalizer()
        
        result = norm.normalize(500)  # 500ms
        assert 0.3 < result.normalized_value < 0.8

    def test_log_scaling(self) -> None:
        """Test log scaling method is used."""
        norm = LatencyNormalizer()
        
        result = norm.normalize(1000)
        assert result.method == NormalizationMethod.LOG


class TestCostNormalizer:
    """Tests for CostNormalizer."""

    def test_free_model(self) -> None:
        """Test free models score 1.0."""
        norm = CostNormalizer()
        
        result = norm.normalize(0)
        assert result.normalized_value == 1.0

    def test_cheap_model(self) -> None:
        """Test cheap models score high."""
        norm = CostNormalizer()
        
        result = norm.normalize(0.1)  # $0.10/M tokens
        assert result.normalized_value > 0.9

    def test_expensive_model(self) -> None:
        """Test expensive models score low."""
        norm = CostNormalizer()
        
        result = norm.normalize(60)  # $60/M tokens
        assert result.normalized_value == 0.0


class TestContextLengthNormalizer:
    """Tests for ContextLengthNormalizer."""

    def test_large_context(self) -> None:
        """Test large context scores high."""
        norm = ContextLengthNormalizer()
        
        result = norm.normalize(1000000)
        assert result.normalized_value == 1.0

    def test_small_context(self) -> None:
        """Test small context scores low."""
        norm = ContextLengthNormalizer()
        
        result = norm.normalize(2048)
        assert result.normalized_value < 0.2


class TestRoutingProfile:
    """Tests for RoutingProfile."""

    def test_weight_normalization(self) -> None:
        """Test weights are normalized to sum to 1.0."""
        profile = RoutingProfile(
            name="test",
            quality_weight=2,
            latency_weight=2,
            cost_weight=2,
        )
        
        total = profile.quality_weight + profile.latency_weight + profile.cost_weight
        assert abs(total - 1.0) < 0.01

    def test_calculate_score(self) -> None:
        """Test composite score calculation."""
        profile = RoutingProfile(
            name="test",
            quality_weight=0.5,
            latency_weight=0.25,
            cost_weight=0.25,
        )
        
        score = profile.calculate_score(quality=1.0, latency=0.5, cost=0.5)
        assert score == 0.75

    def test_meets_constraints(self) -> None:
        """Test constraint checking."""
        profile = RoutingProfile(
            name="test",
            min_quality_threshold=0.5,
            max_latency_ms=1000,
        )
        
        assert profile.meets_constraints(quality_score=0.6, latency_ms=500)
        assert not profile.meets_constraints(quality_score=0.4, latency_ms=500)
        assert not profile.meets_constraints(quality_score=0.6, latency_ms=2000)

    def test_builtin_profiles_exist(self) -> None:
        """Test built-in profiles are defined."""
        assert "quality" in BUILTIN_PROFILES
        assert "balanced" in BUILTIN_PROFILES
        assert "speed" in BUILTIN_PROFILES
        assert "budget" in BUILTIN_PROFILES


class TestCompositeScorer:
    """Tests for CompositeScorer."""

    @pytest.fixture
    def scorer(self) -> CompositeScorer:
        return CompositeScorer()

    @pytest.fixture
    def sample_models(self) -> list[ModelMetrics]:
        return [
            ModelMetrics(
                model_id=1,
                model_name="fast-cheap",
                elo_rating=1100,
                latency_p90=200,
                cost_blended=1.0,
            ),
            ModelMetrics(
                model_id=2,
                model_name="slow-quality",
                elo_rating=1350,
                latency_p90=2000,
                cost_blended=30.0,
            ),
        ]

    def test_score_model(self, scorer: CompositeScorer) -> None:
        """Test scoring a single model."""
        metrics = ModelMetrics(
            model_id=1,
            model_name="test-model",
            elo_rating=1200,
            latency_p90=500,
            cost_blended=5.0,
        )
        
        score = scorer.score_model(metrics, BUILTIN_PROFILES["balanced"])
        
        assert score.model_id == 1
        assert score.model_name == "test-model"
        assert 0 < score.composite_score < 1
        assert 0 < score.quality_score < 1
        assert 0 < score.latency_score < 1
        assert 0 < score.cost_score < 1

    def test_rank_models(
        self, scorer: CompositeScorer, sample_models: list[ModelMetrics]
    ) -> None:
        """Test ranking multiple models."""
        ranked = scorer.rank_models(sample_models, BUILTIN_PROFILES["balanced"])
        
        assert len(ranked) == 2
        assert ranked[0].composite_score >= ranked[1].composite_score

    def test_speed_profile_prefers_fast(
        self, scorer: CompositeScorer, sample_models: list[ModelMetrics]
    ) -> None:
        """Test speed profile prefers faster models."""
        ranked = scorer.rank_models(sample_models, BUILTIN_PROFILES["speed"])
        
        assert ranked[0].model_name == "fast-cheap"

    def test_quality_profile_prefers_quality(
        self, scorer: CompositeScorer, sample_models: list[ModelMetrics]
    ) -> None:
        """Test quality profile prefers higher quality models."""
        ranked = scorer.rank_models(sample_models, BUILTIN_PROFILES["quality"])
        
        assert ranked[0].model_name == "slow-quality"


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    def test_initial_state_closed(self) -> None:
        """Test circuit starts closed."""
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available()

    def test_opens_after_failures(self) -> None:
        """Test circuit opens after threshold failures."""
        cb = CircuitBreaker(failure_threshold=3)
        
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert not cb.is_available()

    def test_success_resets(self) -> None:
        """Test success resets failure count."""
        cb = CircuitBreaker(failure_threshold=3)
        
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        
        assert cb.state == CircuitState.CLOSED


class TestRouter:
    """Tests for Router."""

    @pytest.fixture
    def router(self) -> Router:
        return Router()

    @pytest.fixture
    def sample_models(self) -> list[ModelMetrics]:
        return [
            ModelMetrics(model_id=1, model_name="model-a", elo_rating=1200, latency_p90=500, cost_blended=5.0),
            ModelMetrics(model_id=2, model_name="model-b", elo_rating=1100, latency_p90=300, cost_blended=2.0),
        ]

    def test_route_selects_best(
        self, router: Router, sample_models: list[ModelMetrics]
    ) -> None:
        """Test routing selects best model."""
        result = router.route(sample_models, "balanced")
        
        assert result is not None
        assert result.selected_model is not None
        assert result.routing_time_ms > 0

    def test_route_provides_fallbacks(
        self, router: Router, sample_models: list[ModelMetrics]
    ) -> None:
        """Test routing provides fallback models."""
        result = router.route(sample_models, "balanced")
        
        assert len(result.fallback_models) > 0

    def test_route_with_fallback_excludes_failed(
        self, router: Router, sample_models: list[ModelMetrics]
    ) -> None:
        """Test fallback routing excludes failed models."""
        result = router.route_with_fallback(
            sample_models, "balanced", failed_model_ids=[1]
        )
        
        assert result.selected_model.model_id != 1

    def test_circuit_breaker_integration(
        self, router: Router, sample_models: list[ModelMetrics]
    ) -> None:
        """Test circuit breaker affects routing."""
        # Open circuit for model 1
        for _ in range(5):
            router.record_failure(1)
        
        result = router.route(sample_models, "balanced")
        
        # Should prefer model 2 since model 1's circuit is open
        assert result.selected_model.model_id == 2
