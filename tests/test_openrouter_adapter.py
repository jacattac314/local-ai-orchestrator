"""Tests for OpenRouter adapter."""

import pytest

from orchestrator.adapters.openrouter import OpenRouterAdapter


class TestOpenRouterAdapter:
    """Tests for OpenRouterAdapter."""

    def test_source_name(self) -> None:
        """Test source name property."""
        adapter = OpenRouterAdapter()
        assert adapter.source_name == "openrouter"

    def test_sync_interval(self) -> None:
        """Test sync interval property."""
        adapter = OpenRouterAdapter()
        assert adapter.sync_interval_minutes == 5

    def test_validate_response_valid(self, sample_openrouter_response: dict) -> None:
        """Test response validation with valid data."""
        adapter = OpenRouterAdapter()
        assert adapter.validate_response(sample_openrouter_response) is True

    def test_validate_response_invalid(self) -> None:
        """Test response validation with invalid data."""
        adapter = OpenRouterAdapter()
        assert adapter.validate_response({}) is False
        assert adapter.validate_response({"data": "not a list"}) is False
        assert adapter.validate_response(None) is False  # type: ignore

    def test_parse_response(self, sample_openrouter_response: dict) -> None:
        """Test parsing a valid response."""
        adapter = OpenRouterAdapter()
        metrics = adapter.parse_response(sample_openrouter_response)

        assert len(metrics) > 0

        # Check we got metrics for both models
        model_names = {m.model_name for m in metrics}
        assert "openai/gpt-4" in model_names
        assert "anthropic/claude-3-opus" in model_names

    def test_parse_pricing_metrics(self, sample_openrouter_response: dict) -> None:
        """Test that pricing metrics are correctly extracted."""
        adapter = OpenRouterAdapter()
        metrics = adapter.parse_response(sample_openrouter_response)

        # Find GPT-4 blended cost
        gpt4_cost = [
            m for m in metrics
            if m.model_name == "openai/gpt-4" and m.metric_type == "cost_blended_per_million"
        ]
        assert len(gpt4_cost) == 1

        # Expected: (0.00003 * 1M * 0.7) + (0.00006 * 1M * 0.3) = 21 + 18 = 39
        assert gpt4_cost[0].value == pytest.approx(39.0, rel=0.01)

    def test_parse_latency_metrics(self, sample_openrouter_response: dict) -> None:
        """Test that latency metrics are correctly extracted."""
        adapter = OpenRouterAdapter()
        metrics = adapter.parse_response(sample_openrouter_response)

        # Find GPT-4 p90 latency
        gpt4_latency = [
            m for m in metrics
            if m.model_name == "openai/gpt-4" and m.metric_type == "latency_p90_ms"
        ]
        assert len(gpt4_latency) == 1
        assert gpt4_latency[0].value == 1200.0  # p90 value

    def test_parse_ttft_metrics(self, sample_openrouter_response: dict) -> None:
        """Test that TTFT metrics are extracted when available."""
        adapter = OpenRouterAdapter()
        metrics = adapter.parse_response(sample_openrouter_response)

        # GPT-4 has TTFT data
        gpt4_ttft = [
            m for m in metrics
            if m.model_name == "openai/gpt-4" and m.metric_type == "ttft_p90_ms"
        ]
        assert len(gpt4_ttft) == 1
        assert gpt4_ttft[0].value == 200.0

    def test_parse_context_length(self, sample_openrouter_response: dict) -> None:
        """Test that context length is extracted."""
        adapter = OpenRouterAdapter()
        metrics = adapter.parse_response(sample_openrouter_response)

        claude_context = [
            m for m in metrics
            if m.model_name == "anthropic/claude-3-opus" and m.metric_type == "context_length"
        ]
        assert len(claude_context) == 1
        assert claude_context[0].value == 200000.0

    def test_parse_empty_response(self) -> None:
        """Test parsing an empty valid response."""
        adapter = OpenRouterAdapter()
        metrics = adapter.parse_response({"data": []})
        assert metrics == []

    def test_metric_source_is_set(self, sample_openrouter_response: dict) -> None:
        """Test that all metrics have the correct source."""
        adapter = OpenRouterAdapter()
        metrics = adapter.parse_response(sample_openrouter_response)

        for metric in metrics:
            assert metric.source == "openrouter"
