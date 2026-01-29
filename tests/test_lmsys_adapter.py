"""Tests for LMSYS adapter."""

import pytest

from orchestrator.adapters.lmsys import LMSYSAdapter


@pytest.fixture
def lmsys_adapter() -> LMSYSAdapter:
    """Create a LMSYS adapter instance."""
    return LMSYSAdapter()


@pytest.fixture
def sample_lmsys_csv() -> str:
    """Sample LMSYS CSV data."""
    return """Model,Arena Elo,95% CI Lower,95% CI Upper
gpt-4-turbo,1290,1285,1295
claude-3-opus,1265,1260,1270
gpt-4,1250,1245,1255
claude-3-sonnet,1210,1205,1215
gemini-pro,1180,1175,1185
"""


@pytest.fixture
def sample_lmsys_gradio_json() -> dict:
    """Sample LMSYS Gradio JSON config."""
    return {
        "components": [
            {
                "type": "dataframe",
                "props": {
                    "value": {
                        "headers": ["Model", "Arena Elo"],
                        "data": [
                            ["gpt-4-turbo", "1290"],
                            ["claude-3-opus", "1265"],
                        ],
                    }
                },
            }
        ]
    }


class TestLMSYSAdapter:
    """Tests for LMSYSAdapter."""

    def test_source_name(self, lmsys_adapter: LMSYSAdapter) -> None:
        """Test source name is correct."""
        assert lmsys_adapter.source_name == "lmsys"

    def test_sync_interval(self, lmsys_adapter: LMSYSAdapter) -> None:
        """Test sync interval is 6 hours."""
        assert lmsys_adapter.sync_interval_minutes == 360

    def test_validate_response_csv(self, lmsys_adapter: LMSYSAdapter, sample_lmsys_csv: str) -> None:
        """Test CSV response validation."""
        data = {"format": "csv", "data": sample_lmsys_csv}
        assert lmsys_adapter.validate_response(data) is True

    def test_validate_response_json(self, lmsys_adapter: LMSYSAdapter, sample_lmsys_gradio_json: dict) -> None:
        """Test JSON response validation."""
        data = {"format": "json", "data": sample_lmsys_gradio_json}
        assert lmsys_adapter.validate_response(data) is True

    def test_validate_response_invalid(self, lmsys_adapter: LMSYSAdapter) -> None:
        """Test invalid response validation."""
        assert lmsys_adapter.validate_response({}) is False
        assert lmsys_adapter.validate_response({"format": "invalid"}) is False

    def test_parse_csv(self, lmsys_adapter: LMSYSAdapter, sample_lmsys_csv: str) -> None:
        """Test CSV parsing."""
        data = {"format": "csv", "data": sample_lmsys_csv}
        metrics = lmsys_adapter.parse_response(data)

        # Should have ELO rating for each model + uncertainty metric
        assert len(metrics) >= 5  # At least 5 ELO ratings

        # Check first model
        gpt4_metrics = [m for m in metrics if "gpt-4-turbo" in m.model_name]
        assert len(gpt4_metrics) >= 1
        
        elo_metric = next(m for m in gpt4_metrics if m.metric_type == "elo_rating")
        assert elo_metric.value == 1290
        assert elo_metric.source == "lmsys"

    def test_parse_csv_extracts_uncertainty(self, lmsys_adapter: LMSYSAdapter, sample_lmsys_csv: str) -> None:
        """Test that CSV parsing extracts uncertainty metrics."""
        data = {"format": "csv", "data": sample_lmsys_csv}
        metrics = lmsys_adapter.parse_response(data)

        uncertainty_metrics = [m for m in metrics if m.metric_type == "elo_uncertainty"]
        # Should have uncertainty for each model with CI data
        assert len(uncertainty_metrics) >= 1

    def test_parse_gradio_json(self, lmsys_adapter: LMSYSAdapter, sample_lmsys_gradio_json: dict) -> None:
        """Test Gradio JSON parsing."""
        data = {"format": "json", "data": sample_lmsys_gradio_json}
        metrics = lmsys_adapter.parse_response(data)

        assert len(metrics) >= 2

        gpt4_metrics = [m for m in metrics if "gpt-4-turbo" in m.model_name]
        assert len(gpt4_metrics) >= 1

        elo_metric = gpt4_metrics[0]
        assert elo_metric.value == 1290
        assert elo_metric.metric_type == "elo_rating"

    def test_cache_data_age(self, lmsys_adapter: LMSYSAdapter) -> None:
        """Test cache age tracking."""
        # Initially no cache
        assert lmsys_adapter.cached_data_age_hours is None
