"""Abstract base class for benchmark data sources."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RawMetric:
    """
    Raw metric data from a benchmark source.

    Represents a single metric measurement before normalization
    and entity resolution.
    """

    model_name: str
    """Original model name from the source."""

    metric_type: str
    """Type of metric (e.g., 'elo', 'latency_p90', 'cost_per_million')."""

    value: float
    """Metric value."""

    source: str
    """Source identifier (e.g., 'openrouter', 'lmsys', 'huggingface')."""

    timestamp: datetime = field(default_factory=datetime.utcnow)
    """When the metric was collected."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional metadata from the source."""

    def __repr__(self) -> str:
        return f"RawMetric({self.model_name}, {self.metric_type}={self.value})"


class BenchmarkSource(ABC):
    """
    Abstract base class for benchmark data sources.

    Implement this class to add new data sources for model
    benchmarks, pricing, latency, or other metrics.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """
        Unique identifier for this source.

        Returns:
            Source name (e.g., 'openrouter', 'lmsys')
        """
        ...

    @property
    @abstractmethod
    def sync_interval_minutes(self) -> int:
        """
        Recommended sync interval in minutes.

        Returns:
            Minutes between syncs
        """
        ...

    @abstractmethod
    async def fetch_data(self) -> dict[str, Any]:
        """
        Fetch raw data from the source.

        Returns:
            Raw response data from the source API

        Raises:
            Exception: On fetch failure
        """
        ...

    @abstractmethod
    def parse_response(self, data: dict[str, Any]) -> list[RawMetric]:
        """
        Parse raw response into RawMetric objects.

        Args:
            data: Raw response from fetch_data()

        Returns:
            List of parsed metrics
        """
        ...

    async def fetch_and_parse(self) -> list[RawMetric]:
        """
        Convenience method to fetch and parse in one call.

        Returns:
            List of parsed metrics
        """
        data = await self.fetch_data()
        return self.parse_response(data)

    def validate_response(self, data: dict[str, Any]) -> bool:
        """
        Validate the raw response structure.

        Override this to add source-specific validation.

        Args:
            data: Raw response data

        Returns:
            True if valid, False otherwise
        """
        return bool(data)
