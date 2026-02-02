"""Tests for Ollama adapter."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from orchestrator.adapters.ollama import OllamaAdapter, OllamaModel


class TestOllamaModel:
    """Tests for OllamaModel dataclass."""

    def test_size_gb_calculation(self) -> None:
        """Test size_gb property calculates correctly."""
        model = OllamaModel(
            name="llama3.2",
            model="llama3.2",
            modified_at="2025-01-01T00:00:00Z",
            size=4 * (1024 ** 3),  # 4 GB
            digest="sha256:abc123",
        )
        assert model.size_gb == pytest.approx(4.0, rel=0.01)

    def test_display_name_basic(self) -> None:
        """Test display_name with no additional metadata."""
        model = OllamaModel(
            name="llama3.2",
            model="llama3.2",
            modified_at="2025-01-01T00:00:00Z",
            size=0,
            digest="sha256:abc123",
        )
        assert model.display_name == "llama3.2"

    def test_display_name_with_params_and_quant(self) -> None:
        """Test display_name with parameter size and quantization."""
        model = OllamaModel(
            name="llama3.2",
            model="llama3.2",
            modified_at="2025-01-01T00:00:00Z",
            size=0,
            digest="sha256:abc123",
            parameter_size="7B",
            quantization="Q4_K_M",
        )
        assert model.display_name == "llama3.2 (7B) [Q4_K_M]"


class TestOllamaAdapter:
    """Tests for OllamaAdapter."""

    def test_source_name(self) -> None:
        """Test source name property."""
        adapter = OllamaAdapter()
        assert adapter.source_name == "ollama"

    def test_sync_interval(self) -> None:
        """Test sync interval is 5 minutes."""
        adapter = OllamaAdapter()
        assert adapter.sync_interval_minutes == 5

    def test_default_host(self) -> None:
        """Test default host configuration."""
        adapter = OllamaAdapter()
        assert adapter.host == "http://localhost:11434"

    def test_custom_host(self) -> None:
        """Test custom host configuration."""
        adapter = OllamaAdapter(host="http://custom:8080")
        assert adapter.host == "http://custom:8080"

    def test_is_available_initially_false(self) -> None:
        """Test is_available is False before first sync."""
        adapter = OllamaAdapter()
        assert adapter.is_available is False

    @pytest.mark.asyncio
    async def test_check_connection_success(self) -> None:
        """Test successful connection check."""
        adapter = OllamaAdapter()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(adapter._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            result = await adapter.check_connection()

        assert result is True
        mock_get.assert_called_once_with("http://localhost:11434/api/version")

    @pytest.mark.asyncio
    async def test_check_connection_failure(self) -> None:
        """Test failed connection check."""
        adapter = OllamaAdapter()

        with patch.object(adapter._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Connection refused")
            result = await adapter.check_connection()

        assert result is False

    @pytest.mark.asyncio
    async def test_fetch_data_success(self, sample_ollama_response: dict) -> None:
        """Test successful data fetch."""
        adapter = OllamaAdapter()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_ollama_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(adapter._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            data = await adapter.fetch_data()

        assert data == sample_ollama_response
        assert adapter.is_available is True

    @pytest.mark.asyncio
    async def test_fetch_data_connection_error(self) -> None:
        """Test graceful handling when Ollama is not running."""
        import httpx
        adapter = OllamaAdapter()

        with patch.object(adapter._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ConnectError("Connection refused")
            data = await adapter.fetch_data()

        assert data == {"models": []}

    def test_parse_response_empty(self) -> None:
        """Test parsing empty response."""
        adapter = OllamaAdapter()
        metrics = adapter.parse_response({"models": []})
        assert metrics == []

    def test_parse_response_with_models(self, sample_ollama_response: dict) -> None:
        """Test parsing response with models."""
        adapter = OllamaAdapter()
        metrics = adapter.parse_response(sample_ollama_response)

        assert len(metrics) > 0

        # Check we got metrics for both models
        model_names = {m.model_name for m in metrics}
        assert "llama3.2:7b" in model_names
        assert "mistral:7b-instruct" in model_names

    def test_parse_response_creates_correct_metric_types(
        self, sample_ollama_response: dict
    ) -> None:
        """Test that all expected metric types are created."""
        adapter = OllamaAdapter()
        metrics = adapter.parse_response(sample_ollama_response)

        llama_metrics = [m for m in metrics if m.model_name == "llama3.2:7b"]
        metric_types = {m.metric_type for m in llama_metrics}

        assert "quality_score" in metric_types
        assert "context_window" in metric_types
        assert "cost_per_million_input" in metric_types
        assert "cost_per_million_output" in metric_types
        assert "latency_p50" in metric_types

    def test_parse_response_zero_cost(self, sample_ollama_response: dict) -> None:
        """Test that local models have zero cost."""
        adapter = OllamaAdapter()
        metrics = adapter.parse_response(sample_ollama_response)

        cost_metrics = [
            m for m in metrics
            if m.metric_type in ("cost_per_million_input", "cost_per_million_output")
        ]

        for metric in cost_metrics:
            assert metric.value == 0.0

    def test_parse_response_local_flag(self, sample_ollama_response: dict) -> None:
        """Test that quality metrics have is_local flag."""
        adapter = OllamaAdapter()
        metrics = adapter.parse_response(sample_ollama_response)

        quality_metrics = [m for m in metrics if m.metric_type == "quality_score"]

        for metric in quality_metrics:
            assert metric.metadata.get("is_local") is True

    def test_metric_source_is_set(self, sample_ollama_response: dict) -> None:
        """Test that all metrics have the correct source."""
        adapter = OllamaAdapter()
        metrics = adapter.parse_response(sample_ollama_response)

        for metric in metrics:
            assert metric.source == "ollama"

    def test_cached_models_empty_initially(self) -> None:
        """Test cached models list is empty initially."""
        adapter = OllamaAdapter()
        assert adapter.get_cached_models() == []

    def test_cached_models_populated_after_parse(
        self, sample_ollama_response: dict
    ) -> None:
        """Test cached models are populated after parsing."""
        adapter = OllamaAdapter()
        adapter.parse_response(sample_ollama_response)

        cached = adapter.get_cached_models()
        assert len(cached) == 2
        assert any(m.name == "llama3.2:7b" for m in cached)


class TestQualityEstimation:
    """Tests for quality score estimation logic."""

    def test_quality_llama_family(self) -> None:
        """Test quality estimation for llama family."""
        adapter = OllamaAdapter()
        model = OllamaModel(
            name="llama3.2:7b",
            model="llama3.2:7b",
            modified_at="",
            size=0,
            digest="",
            family="llama",
            parameter_size="7B",
        )
        score = adapter._estimate_quality(model)
        # Base 75 (llama) + 2 (7B) = 77
        assert score == pytest.approx(77.0, rel=0.01)

    def test_quality_mistral_large(self) -> None:
        """Test quality for large mistral model."""
        adapter = OllamaAdapter()
        model = OllamaModel(
            name="mistral:70b",
            model="mistral:70b",
            modified_at="",
            size=0,
            digest="",
            family="mistral",
            parameter_size="70B",
        )
        score = adapter._estimate_quality(model)
        # Base 76 (mistral) + 10 (70B) = 86
        assert score == pytest.approx(86.0, rel=0.01)

    def test_quality_quantization_penalty(self) -> None:
        """Test quality reduction for quantization."""
        adapter = OllamaAdapter()
        model = OllamaModel(
            name="llama3.2:7b-q4",
            model="llama3.2:7b-q4",
            modified_at="",
            size=0,
            digest="",
            family="llama",
            parameter_size="7B",
            quantization="Q4_K_M",
        )
        score = adapter._estimate_quality(model)
        # Base 75 (llama) + 2 (7B) - 3 (Q4) = 74
        assert score == pytest.approx(74.0, rel=0.01)

    def test_quality_clamped_to_range(self) -> None:
        """Test quality score is clamped between 0 and 100."""
        adapter = OllamaAdapter()
        # Very small unknown model
        model = OllamaModel(
            name="tiny-unknown",
            model="tiny-unknown",
            modified_at="",
            size=0,
            digest="",
            family="",
            parameter_size="1B",
            quantization="Q3_K_S",
        )
        score = adapter._estimate_quality(model)
        assert 0 <= score <= 100


class TestContextWindowEstimation:
    """Tests for context window estimation."""

    def test_context_window_llama(self) -> None:
        """Test context window for llama models."""
        adapter = OllamaAdapter()
        model = OllamaModel(
            name="llama3.2",
            model="llama3.2",
            modified_at="",
            size=0,
            digest="",
            family="llama",
        )
        window = adapter._estimate_context_window(model)
        assert window == 8192

    def test_context_window_qwen(self) -> None:
        """Test context window for qwen models."""
        adapter = OllamaAdapter()
        model = OllamaModel(
            name="qwen2",
            model="qwen2",
            modified_at="",
            size=0,
            digest="",
            family="qwen",
        )
        window = adapter._estimate_context_window(model)
        assert window == 32768

    def test_context_window_unknown(self) -> None:
        """Test default context window for unknown models."""
        adapter = OllamaAdapter()
        model = OllamaModel(
            name="unknown-model",
            model="unknown-model",
            modified_at="",
            size=0,
            digest="",
            family="",
        )
        window = adapter._estimate_context_window(model)
        assert window == 4096  # Conservative default


class TestOllamaOperations:
    """Tests for Ollama API operations."""

    @pytest.mark.asyncio
    async def test_pull_model_success(self) -> None:
        """Test successful model pull."""
        adapter = OllamaAdapter()

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "success"}

        with patch.object(adapter._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await adapter.pull_model("llama3.2")

        assert result == {"status": "success"}
        mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_pull_model_error(self) -> None:
        """Test model pull error handling."""
        adapter = OllamaAdapter()

        with patch.object(adapter._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = Exception("Network error")
            result = await adapter.pull_model("llama3.2")

        assert "error" in result

    @pytest.mark.asyncio
    async def test_generate_success(self) -> None:
        """Test successful generation."""
        adapter = OllamaAdapter()

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Hello!"}
        mock_response.raise_for_status = MagicMock()

        with patch.object(adapter._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await adapter.generate("llama3.2", "Hello")

        assert result == {"response": "Hello!"}

    @pytest.mark.asyncio
    async def test_chat_success(self) -> None:
        """Test successful chat completion."""
        adapter = OllamaAdapter()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"role": "assistant", "content": "Hello!"}
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(adapter._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await adapter.chat(
                "llama3.2",
                [{"role": "user", "content": "Hello"}]
            )

        assert "message" in result

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        """Test closing the adapter."""
        adapter = OllamaAdapter()

        with patch.object(adapter._client, 'aclose', new_callable=AsyncMock) as mock_close:
            await adapter.close()
            mock_close.assert_called_once()


# Fixtures

@pytest.fixture
def sample_ollama_response() -> dict:
    """Sample Ollama API response for testing."""
    return {
        "models": [
            {
                "name": "llama3.2:7b",
                "model": "llama3.2:7b",
                "modified_at": "2025-01-15T10:30:00Z",
                "size": 4_000_000_000,  # ~4GB
                "digest": "sha256:abc123def456",
                "details": {
                    "family": "llama",
                    "parameter_size": "7B",
                    "quantization_level": "Q4_K_M",
                },
            },
            {
                "name": "mistral:7b-instruct",
                "model": "mistral:7b-instruct",
                "modified_at": "2025-01-10T08:00:00Z",
                "size": 4_500_000_000,  # ~4.5GB
                "digest": "sha256:789xyz",
                "details": {
                    "family": "mistral",
                    "parameter_size": "7B",
                    "quantization_level": "Q5_K_M",
                },
            },
        ]
    }
