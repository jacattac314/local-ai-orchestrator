"""OpenRouter API adapter for model pricing and latency data."""

import logging
import os
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from orchestrator.adapters.base import BenchmarkSource, RawMetric
from orchestrator.http.client import SyncHttpClient

logger = logging.getLogger(__name__)


# Pydantic models for response validation
class LatencyStats(BaseModel):
    """Latency statistics from OpenRouter."""

    p50: float | None = None
    p90: float | None = None
    p95: float | None = None
    p99: float | None = None


class Pricing(BaseModel):
    """Pricing information from OpenRouter."""

    prompt: str = "0"
    completion: str = "0"
    request: str = "0"
    image: str = "0"


class OpenRouterModel(BaseModel):
    """Model data from OpenRouter API."""

    id: str
    name: str
    description: str | None = None
    context_length: int | None = None
    pricing: Pricing = Field(default_factory=Pricing)
    top_provider: dict[str, Any] = Field(default_factory=dict)
    per_request_limits: dict[str, Any] | None = None

    # Latency data might be nested
    class Config:
        extra = "allow"


class OpenRouterResponse(BaseModel):
    """Response from OpenRouter /api/v1/models endpoint."""

    data: list[OpenRouterModel]


class OpenRouterAdapter(BenchmarkSource):
    """
    Adapter for OpenRouter API.

    Fetches model information including:
    - Pricing (prompt/completion costs)
    - Latency (p50, p90, p95, p99)
    - Context length
    - Provider information
    """

    API_URL = "https://openrouter.ai/api/v1/models"

    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialize the OpenRouter adapter.

        Args:
            api_key: OpenRouter API key (or from OPENROUTER_API_KEY env var)
        """
        self._api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self._api_key:
            logger.warning("No OpenRouter API key provided - requests may be rate limited")

    @property
    def source_name(self) -> str:
        return "openrouter"

    @property
    def sync_interval_minutes(self) -> int:
        return 5  # Sync every 5 minutes

    async def fetch_data(self) -> dict[str, Any]:
        """Fetch model data from OpenRouter API."""
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        client = SyncHttpClient(headers=headers)
        try:
            response = client.get_json(self.API_URL)
            return response
        finally:
            client.close()

    def validate_response(self, data: dict[str, Any]) -> bool:
        """Validate the OpenRouter response structure."""
        if not isinstance(data, dict):
            return False
        if "data" not in data:
            return False
        if not isinstance(data["data"], list):
            return False
        return True

    def parse_response(self, data: dict[str, Any]) -> list[RawMetric]:
        """Parse OpenRouter response into RawMetric objects."""
        if not self.validate_response(data):
            logger.error("Invalid OpenRouter response structure")
            return []

        metrics: list[RawMetric] = []
        timestamp = datetime.utcnow()

        try:
            response = OpenRouterResponse(**data)
        except Exception as e:
            logger.error(f"Failed to parse OpenRouter response: {e}")
            return []

        for model in response.data:
            model_name = model.id
            metadata = {
                "name": model.name,
                "description": model.description,
                "context_length": model.context_length,
            }

            # Parse pricing metrics
            pricing_metrics = self._parse_pricing(model, model_name, timestamp, metadata)
            metrics.extend(pricing_metrics)

            # Parse latency metrics
            latency_metrics = self._parse_latency(model, model_name, timestamp, metadata)
            metrics.extend(latency_metrics)

            # Add context length metric
            if model.context_length:
                metrics.append(
                    RawMetric(
                        model_name=model_name,
                        metric_type="context_length",
                        value=float(model.context_length),
                        source=self.source_name,
                        timestamp=timestamp,
                        metadata=metadata,
                    )
                )

        logger.info(f"Parsed {len(metrics)} metrics from {len(response.data)} models")
        return metrics

    def _parse_pricing(
        self,
        model: OpenRouterModel,
        model_name: str,
        timestamp: datetime,
        metadata: dict[str, Any],
    ) -> list[RawMetric]:
        """
        Parse pricing information from model.

        Calculates:
        - cost_prompt_per_million: Prompt cost per 1M tokens
        - cost_completion_per_million: Completion cost per 1M tokens
        - cost_blended_per_million: 70% prompt / 30% completion weighted average
        """
        metrics: list[RawMetric] = []

        try:
            # OpenRouter prices are per token, convert to per million
            prompt_cost = float(model.pricing.prompt) * 1_000_000
            completion_cost = float(model.pricing.completion) * 1_000_000

            # Prompt cost
            metrics.append(
                RawMetric(
                    model_name=model_name,
                    metric_type="cost_prompt_per_million",
                    value=prompt_cost,
                    source=self.source_name,
                    timestamp=timestamp,
                    metadata=metadata,
                )
            )

            # Completion cost
            metrics.append(
                RawMetric(
                    model_name=model_name,
                    metric_type="cost_completion_per_million",
                    value=completion_cost,
                    source=self.source_name,
                    timestamp=timestamp,
                    metadata=metadata,
                )
            )

            # Blended cost (70% prompt, 30% completion)
            blended_cost = (prompt_cost * 0.7) + (completion_cost * 0.3)
            metrics.append(
                RawMetric(
                    model_name=model_name,
                    metric_type="cost_blended_per_million",
                    value=blended_cost,
                    source=self.source_name,
                    timestamp=timestamp,
                    metadata={**metadata, "blend_ratio": "70/30"},
                )
            )

        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse pricing for {model_name}: {e}")

        return metrics

    def _parse_latency(
        self,
        model: OpenRouterModel,
        model_name: str,
        timestamp: datetime,
        metadata: dict[str, Any],
    ) -> list[RawMetric]:
        """
        Parse latency information from model.

        Extracts p90 latency (with p50 fallback) and TTFT if available.
        """
        metrics: list[RawMetric] = []

        # Try to find latency in top_provider or model extras
        latency_data = model.top_provider.get("latency_last_30m", {})
        if not latency_data:
            # Try model-level extras
            latency_data = getattr(model, "latency_last_30m", {}) or {}

        if latency_data:
            # Primary: p90 latency
            p90 = latency_data.get("p90")
            p50 = latency_data.get("p50")

            latency_value = p90 if p90 is not None else p50
            if latency_value is not None:
                try:
                    metrics.append(
                        RawMetric(
                            model_name=model_name,
                            metric_type="latency_p90_ms",
                            value=float(latency_value),
                            source=self.source_name,
                            timestamp=timestamp,
                            metadata={**metadata, "fallback_used": p90 is None},
                        )
                    )
                except (ValueError, TypeError):
                    pass

        # TTFT (Time to First Token) if available
        ttft_data = model.top_provider.get("ttft_last_30m", {})
        if ttft_data:
            ttft_p90 = ttft_data.get("p90")
            if ttft_p90 is not None:
                try:
                    metrics.append(
                        RawMetric(
                            model_name=model_name,
                            metric_type="ttft_p90_ms",
                            value=float(ttft_p90),
                            source=self.source_name,
                            timestamp=timestamp,
                            metadata=metadata,
                        )
                    )
                except (ValueError, TypeError):
                    pass

        return metrics

    def fetch_and_parse_sync(self) -> list[RawMetric]:
        """
        Synchronous version of fetch_and_parse.

        Useful for scheduler jobs that don't run in async context.
        """
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        client = SyncHttpClient(headers=headers)
        try:
            data = client.get_json(self.API_URL)
            return self.parse_response(data)
        finally:
            client.close()
