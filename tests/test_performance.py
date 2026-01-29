"""Performance benchmarks for routing components.

Run with: pytest -m performance --benchmark-enable
"""

import pytest
import time
from typing import Generator

from orchestrator.routing import CompositeScorer, Router, BUILTIN_PROFILES
from orchestrator.routing.complexity import ComplexityClassifier
from orchestrator.routing.scorer import ModelMetrics


# --- Fixtures ---


@pytest.fixture
def large_model_set() -> list[ModelMetrics]:
    """Generate 100 models for performance testing."""
    import random

    random.seed(42)
    models = []

    providers = ["openai", "anthropic", "google", "meta", "mistral", "cohere"]

    for i in range(100):
        provider = random.choice(providers)
        models.append(
            ModelMetrics(
                model_id=i + 1,
                model_name=f"{provider}/model-{i}",
                elo_rating=random.uniform(1000, 1300),
                latency_p90=random.uniform(50, 2000),
                cost_blended=random.uniform(0.1, 50),
                context_length=random.choice([4096, 8192, 16384, 32768, 128000]),
            )
        )

    return models


@pytest.fixture
def scorer() -> CompositeScorer:
    return CompositeScorer()


@pytest.fixture
def router() -> Router:
    return Router()


@pytest.fixture
def classifier() -> ComplexityClassifier:
    return ComplexityClassifier()


# --- Performance Tests ---


@pytest.mark.performance
class TestScorerPerformance:
    """Benchmark scoring engine throughput."""

    def test_score_100_models(
        self, scorer: CompositeScorer, large_model_set: list[ModelMetrics]
    ) -> None:
        """Benchmark scoring 100 models."""
        profile = BUILTIN_PROFILES["balanced"]

        start = time.perf_counter()
        iterations = 100

        for _ in range(iterations):
            scores = scorer.rank_models(large_model_set, profile)

        elapsed = time.perf_counter() - start
        avg_ms = (elapsed / iterations) * 1000

        print(f"\nScoring 100 models: {avg_ms:.2f}ms average")
        assert avg_ms < 100, f"Scoring too slow: {avg_ms:.2f}ms"

    def test_score_single_model_throughput(
        self, scorer: CompositeScorer, large_model_set: list[ModelMetrics]
    ) -> None:
        """Benchmark single model scoring throughput."""
        profile = BUILTIN_PROFILES["balanced"]
        model = large_model_set[0]

        start = time.perf_counter()
        iterations = 10000

        for _ in range(iterations):
            _ = scorer.score_model(model, profile)

        elapsed = time.perf_counter() - start
        ops_per_sec = iterations / elapsed

        print(f"\nSingle model scoring: {ops_per_sec:.0f} ops/sec")
        assert ops_per_sec > 10000, f"Throughput too low: {ops_per_sec:.0f}"


@pytest.mark.performance
class TestRouterPerformance:
    """Benchmark router selection speed."""

    def test_route_100_models(
        self, router: Router, large_model_set: list[ModelMetrics]
    ) -> None:
        """Benchmark routing with 100 models."""
        start = time.perf_counter()
        iterations = 100

        for _ in range(iterations):
            result = router.route(large_model_set, profile="balanced")

        elapsed = time.perf_counter() - start
        avg_ms = (elapsed / iterations) * 1000

        print(f"\nRouting 100 models: {avg_ms:.2f}ms average")
        assert avg_ms < 150, f"Routing too slow: {avg_ms:.2f}ms"

    def test_fallback_routing_speed(
        self, router: Router, large_model_set: list[ModelMetrics]
    ) -> None:
        """Benchmark fallback routing."""
        start = time.perf_counter()
        iterations = 50

        for _ in range(iterations):
            # Simulate cascading fallback
            result = router.route(large_model_set, profile="quality")
            if result:
                result = router.route_with_fallback(
                    large_model_set,
                    profile="quality",
                    failed_model_ids=[result.model_id],
                )

        elapsed = time.perf_counter() - start
        avg_ms = (elapsed / iterations) * 1000

        print(f"\nFallback routing: {avg_ms:.2f}ms average")
        assert avg_ms < 250, f"Fallback too slow: {avg_ms:.2f}ms"


@pytest.mark.performance
class TestComplexityPerformance:
    """Benchmark complexity classification speed."""

    def test_classify_short_prompt(self, classifier: ComplexityClassifier) -> None:
        """Benchmark short prompt classification."""
        prompt = "What is the capital of France?"

        start = time.perf_counter()
        iterations = 1000

        for _ in range(iterations):
            _ = classifier.classify(prompt)

        elapsed = time.perf_counter() - start
        ops_per_sec = iterations / elapsed

        print(f"\nShort prompt classification: {ops_per_sec:.0f} ops/sec")
        assert ops_per_sec > 5000, f"Classification too slow: {ops_per_sec:.0f}"

    def test_classify_long_prompt(self, classifier: ComplexityClassifier) -> None:
        """Benchmark long prompt classification."""
        prompt = """
        Please analyze the following research paper and provide:
        1. A comprehensive summary of the methodology
        2. Critical analysis of the statistical approaches
        3. Comparison with similar studies in the field
        4. Recommendations for future research directions
        
        The paper discusses the implementation of transformer architectures
        for natural language processing tasks, specifically focusing on
        attention mechanisms and their computational complexity...
        """ + " Lorem ipsum dolor sit amet. " * 100

        start = time.perf_counter()
        iterations = 500

        for _ in range(iterations):
            _ = classifier.classify(prompt)

        elapsed = time.perf_counter() - start
        ops_per_sec = iterations / elapsed

        print(f"\nLong prompt classification: {ops_per_sec:.0f} ops/sec")
        assert ops_per_sec > 500, f"Classification too slow: {ops_per_sec:.0f}"


@pytest.mark.performance
class TestMemoryUsage:
    """Test memory efficiency."""

    def test_scorer_memory_with_many_models(
        self, large_model_set: list[ModelMetrics]
    ) -> None:
        """Test scorer doesn't leak memory."""
        import sys

        scorer = CompositeScorer()
        profile = BUILTIN_PROFILES["balanced"]

        # Get baseline
        baseline = sys.getsizeof(scorer)

        # Run many iterations
        for _ in range(100):
            _ = scorer.rank_models(large_model_set, profile)

        # Check scorer size hasn't grown significantly
        after = sys.getsizeof(scorer)
        growth = after - baseline

        print(f"\nScorer memory growth: {growth} bytes")
        assert growth < 10000, f"Potential memory leak: {growth} bytes growth"
