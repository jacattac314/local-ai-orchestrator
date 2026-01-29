"""Tests for HuggingFace adapter."""

import pytest
import tempfile
from pathlib import Path

from orchestrator.adapters.huggingface import HuggingFaceAdapter


@pytest.fixture
def hf_adapter(tmp_path: Path) -> HuggingFaceAdapter:
    """Create a HuggingFace adapter with temp cache dir."""
    return HuggingFaceAdapter(cache_dir=tmp_path)


@pytest.fixture
def sample_hf_results() -> dict:
    """Sample HuggingFace results data."""
    return {
        "format": "json",
        "data": {
            "models": [
                {
                    "model": "meta-llama/Llama-3-70B-Instruct",
                    "mmlu_pro": 0.72,
                    "ifeval": 0.85,
                    "bbh": 0.78,
                    "gpqa": 0.42,
                    "math": 0.55,
                    "musr": 0.62,
                },
                {
                    "model": "mistralai/Mixtral-8x22B-Instruct-v0.1",
                    "mmlu_pro": 0.68,
                    "ifeval": 0.81,
                    "bbh": 0.75,
                    "gpqa": 0.38,
                    "math": 0.48,
                },
            ]
        },
    }


@pytest.fixture
def sample_hf_results_normalized() -> dict:
    """Sample HuggingFace results with normalized scores (0-100)."""
    return {
        "format": "json",
        "data": {
            "results": [
                {
                    "name": "GPT-4o",
                    "results": {
                        "mmlu_pro": {"acc": 85.5},
                        "ifeval": {"score": 92.0},
                    },
                },
            ]
        },
    }


class TestHuggingFaceAdapter:
    """Tests for HuggingFaceAdapter."""

    def test_source_name(self, hf_adapter: HuggingFaceAdapter) -> None:
        """Test source name is correct."""
        assert hf_adapter.source_name == "huggingface"

    def test_sync_interval(self, hf_adapter: HuggingFaceAdapter) -> None:
        """Test sync interval is 24 hours."""
        assert hf_adapter.sync_interval_minutes == 1440

    def test_validate_response_valid(self, hf_adapter: HuggingFaceAdapter, sample_hf_results: dict) -> None:
        """Test valid response validation."""
        assert hf_adapter.validate_response(sample_hf_results) is True

    def test_validate_response_invalid(self, hf_adapter: HuggingFaceAdapter) -> None:
        """Test invalid response validation."""
        assert hf_adapter.validate_response({}) is False
        assert hf_adapter.validate_response({"format": "json"}) is False

    def test_parse_response(self, hf_adapter: HuggingFaceAdapter, sample_hf_results: dict) -> None:
        """Test response parsing."""
        metrics = hf_adapter.parse_response(sample_hf_results)

        # Should have multiple metrics per model
        assert len(metrics) > 0

        # Check Llama model metrics
        llama_metrics = [m for m in metrics if "Llama" in m.model_name]
        assert len(llama_metrics) >= 6  # 6 benchmarks + average

    def test_parse_response_normalizes_scores(self, hf_adapter: HuggingFaceAdapter, sample_hf_results: dict) -> None:
        """Test that scores <= 1.0 are normalized to 0-100."""
        metrics = hf_adapter.parse_response(sample_hf_results)

        for metric in metrics:
            # All benchmark scores should be in 0-100 range
            if metric.metric_type.startswith("benchmark_"):
                assert 0 <= metric.value <= 100, f"{metric.metric_type}: {metric.value}"

    def test_parse_nested_results(self, hf_adapter: HuggingFaceAdapter, sample_hf_results_normalized: dict) -> None:
        """Test parsing nested result structures."""
        metrics = hf_adapter.parse_response(sample_hf_results_normalized)

        assert len(metrics) > 0
        gpt_metrics = [m for m in metrics if "GPT-4o" in m.model_name]
        assert len(gpt_metrics) >= 1

    def test_benchmark_average_calculated(self, hf_adapter: HuggingFaceAdapter, sample_hf_results: dict) -> None:
        """Test that benchmark average is calculated."""
        metrics = hf_adapter.parse_response(sample_hf_results)

        avg_metrics = [m for m in metrics if m.metric_type == "benchmark_average"]
        assert len(avg_metrics) >= 1

    def test_cache_operations(self, hf_adapter: HuggingFaceAdapter, sample_hf_results: dict) -> None:
        """Test cache save and load."""
        # Save to cache
        hf_adapter._save_cache(sample_hf_results)

        # Load from cache
        loaded = hf_adapter._load_cache()
        assert loaded is not None
        assert loaded["format"] == sample_hf_results["format"]

    def test_compute_hash(self, hf_adapter: HuggingFaceAdapter) -> None:
        """Test content hash computation."""
        content1 = "test content"
        content2 = "different content"

        hash1 = hf_adapter._compute_hash(content1)
        hash2 = hf_adapter._compute_hash(content2)

        assert hash1 != hash2
        assert len(hash1) == 16
