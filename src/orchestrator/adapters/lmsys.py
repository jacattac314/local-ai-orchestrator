"""LMSYS Chatbot Arena adapter for ELO ratings."""

import csv
import io
import json
import logging
from datetime import datetime
from typing import Any

from orchestrator.adapters.base import BenchmarkSource, RawMetric
from orchestrator.http.client import SyncHttpClient

logger = logging.getLogger(__name__)


class LMSYSAdapter(BenchmarkSource):
    """
    Adapter for LMSYS Chatbot Arena leaderboard.

    Fetches ELO ratings and confidence intervals from the LMSYS Arena.
    Supports both CSV export and JSON fallback from Gradio config.
    """

    # Primary CSV endpoint (direct export)
    CSV_URL = "https://huggingface.co/spaces/lmsys/chatbot-arena-leaderboard/resolve/main/leaderboard_table.csv"
    
    # Fallback: Gradio config JSON
    GRADIO_URL = "https://lmsys-chatbot-arena-leaderboard.hf.space/config"
    
    # Alternative HF dataset
    HF_DATASET_URL = "https://huggingface.co/datasets/lmsys/chatbot-arena-leaderboard/resolve/main/leaderboard.csv"

    def __init__(self, cache_last_response: bool = True) -> None:
        """
        Initialize the LMSYS adapter.

        Args:
            cache_last_response: Whether to cache last successful response
        """
        self._cache_last_response = cache_last_response
        self._cached_data: dict[str, Any] | None = None
        self._cache_timestamp: datetime | None = None

    @property
    def source_name(self) -> str:
        return "lmsys"

    @property
    def sync_interval_minutes(self) -> int:
        return 360  # 6 hours

    async def fetch_data(self) -> dict[str, Any]:
        """Fetch data from LMSYS (async wrapper for sync method)."""
        return self._fetch_data_sync()

    def _fetch_data_sync(self) -> dict[str, Any]:
        """
        Fetch data from LMSYS with fallback strategy.

        Tries in order:
        1. Direct CSV from HuggingFace Space
        2. HuggingFace Dataset CSV
        3. Gradio config JSON

        Returns:
            Dict with 'format' key ('csv' or 'json') and 'data' key
        """
        client = SyncHttpClient()

        try:
            # Try primary CSV endpoint
            logger.info("Fetching LMSYS leaderboard from primary CSV...")
            response = client.get(self.CSV_URL)
            if response.status_code == 200:
                csv_text = response.text
                if csv_text and "," in csv_text:
                    result = {"format": "csv", "data": csv_text}
                    self._update_cache(result)
                    return result

            # Try HuggingFace dataset
            logger.info("Primary CSV failed, trying HuggingFace dataset...")
            response = client.get(self.HF_DATASET_URL)
            if response.status_code == 200:
                csv_text = response.text
                if csv_text and "," in csv_text:
                    result = {"format": "csv", "data": csv_text}
                    self._update_cache(result)
                    return result

            # Fallback to Gradio JSON
            logger.info("CSV endpoints failed, trying Gradio JSON fallback...")
            return self._fetch_gradio_fallback(client)

        except Exception as e:
            logger.warning(f"LMSYS fetch error: {e}")
            # Try Gradio fallback
            try:
                return self._fetch_gradio_fallback(client)
            except Exception as e2:
                logger.error(f"All LMSYS sources failed: {e2}")
                # Return cached data if available
                if self._cached_data:
                    logger.info("Using cached LMSYS data")
                    return self._cached_data
                raise
        finally:
            client.close()

    def _fetch_gradio_fallback(self, client: SyncHttpClient) -> dict[str, Any]:
        """Fetch from Gradio config as fallback."""
        response = client.get(self.GRADIO_URL)
        response.raise_for_status()
        
        config = response.json()
        result = {"format": "json", "data": config}
        self._update_cache(result)
        return result

    def _update_cache(self, data: dict[str, Any]) -> None:
        """Update the response cache."""
        if self._cache_last_response:
            self._cached_data = data
            self._cache_timestamp = datetime.utcnow()

    def validate_response(self, data: dict[str, Any]) -> bool:
        """Validate the response structure."""
        if not isinstance(data, dict):
            return False
        if "format" not in data or "data" not in data:
            return False
        return data["format"] in ("csv", "json")

    def parse_response(self, data: dict[str, Any]) -> list[RawMetric]:
        """Parse LMSYS response into RawMetric objects."""
        if not self.validate_response(data):
            logger.error("Invalid LMSYS response structure")
            return []

        if data["format"] == "csv":
            return self._parse_csv(data["data"])
        else:
            return self._parse_gradio_json(data["data"])

    def _parse_csv(self, csv_text: str) -> list[RawMetric]:
        """
        Parse CSV format leaderboard data.

        Expected columns (may vary):
        - Model/model_name: Model identifier
        - Arena Elo/elo/rating: ELO rating
        - 95% CI/ci_lower/ci_upper: Confidence intervals
        """
        metrics: list[RawMetric] = []
        timestamp = datetime.utcnow()

        try:
            reader = csv.DictReader(io.StringIO(csv_text))
            
            # Normalize column names (handle different formats)
            for row in reader:
                # Find model name column
                model_name = self._find_column_value(
                    row, 
                    ["Model", "model", "model_name", "name", "Model Name"]
                )
                if not model_name:
                    continue

                # Find ELO rating
                elo_str = self._find_column_value(
                    row,
                    ["Arena Elo", "elo", "Elo", "rating", "Arena Score", "score", "Rating"]
                )
                if not elo_str:
                    continue

                try:
                    elo = float(elo_str.replace(",", ""))
                except (ValueError, AttributeError):
                    continue

                # Extract confidence intervals if available
                ci_lower = self._find_column_value(
                    row, ["CI Lower", "ci_lower", "lower", "95% CI Lower", "-95% CI"]
                )
                ci_upper = self._find_column_value(
                    row, ["CI Upper", "ci_upper", "upper", "95% CI Upper", "+95% CI"]
                )

                metadata: dict[str, Any] = {"raw_row": dict(row)}
                
                if ci_lower and ci_upper:
                    try:
                        lower = float(ci_lower.replace(",", ""))
                        upper = float(ci_upper.replace(",", ""))
                        metadata["ci_lower"] = lower
                        metadata["ci_upper"] = upper
                        metadata["ci_width"] = upper - lower
                    except (ValueError, AttributeError):
                        pass

                # Main ELO metric
                metrics.append(
                    RawMetric(
                        model_name=model_name.strip(),
                        metric_type="elo_rating",
                        value=elo,
                        source=self.source_name,
                        timestamp=timestamp,
                        metadata=metadata,
                    )
                )

                # Add confidence uncertainty as separate metric if available
                if "ci_width" in metadata:
                    # Calculate uncertainty penalty (wider CI = higher uncertainty)
                    uncertainty = metadata["ci_width"] / elo if elo > 0 else 0
                    metrics.append(
                        RawMetric(
                            model_name=model_name.strip(),
                            metric_type="elo_uncertainty",
                            value=uncertainty,
                            source=self.source_name,
                            timestamp=timestamp,
                            metadata={"ci_width": metadata["ci_width"]},
                        )
                    )

            logger.info(f"Parsed {len(metrics)} metrics from LMSYS CSV")
            return metrics

        except Exception as e:
            logger.error(f"Error parsing LMSYS CSV: {e}")
            return []

    def _parse_gradio_json(self, config: dict[str, Any]) -> list[RawMetric]:
        """
        Parse Gradio config JSON as fallback.

        The leaderboard data is typically in the components array.
        """
        metrics: list[RawMetric] = []
        timestamp = datetime.utcnow()

        try:
            # Navigate Gradio config structure
            components = config.get("components", [])
            
            for component in components:
                # Look for dataframe components
                if component.get("type") == "dataframe":
                    props = component.get("props", {})
                    value = props.get("value", {})
                    
                    headers = value.get("headers", [])
                    data = value.get("data", [])
                    
                    if not headers or not data:
                        continue

                    # Find column indices
                    model_idx = self._find_column_index(
                        headers, ["Model", "model", "model_name"]
                    )
                    elo_idx = self._find_column_index(
                        headers, ["Arena Elo", "elo", "Elo", "rating"]
                    )

                    if model_idx is None or elo_idx is None:
                        continue

                    for row in data:
                        if len(row) <= max(model_idx, elo_idx):
                            continue

                        model_name = str(row[model_idx])
                        try:
                            elo = float(str(row[elo_idx]).replace(",", ""))
                        except (ValueError, TypeError):
                            continue

                        metrics.append(
                            RawMetric(
                                model_name=model_name.strip(),
                                metric_type="elo_rating",
                                value=elo,
                                source=self.source_name,
                                timestamp=timestamp,
                                metadata={"source_format": "gradio_json"},
                            )
                        )

            logger.info(f"Parsed {len(metrics)} metrics from LMSYS Gradio JSON")
            return metrics

        except Exception as e:
            logger.error(f"Error parsing LMSYS Gradio JSON: {e}")
            return []

    def _find_column_value(
        self, row: dict[str, str], possible_names: list[str]
    ) -> str | None:
        """Find a column value by trying multiple possible column names."""
        for name in possible_names:
            if name in row and row[name]:
                return row[name]
            # Case-insensitive fallback
            for key in row:
                if key.lower() == name.lower() and row[key]:
                    return row[key]
        return None

    def _find_column_index(
        self, headers: list[str], possible_names: list[str]
    ) -> int | None:
        """Find column index by trying multiple possible names."""
        for name in possible_names:
            for idx, header in enumerate(headers):
                if header.lower() == name.lower():
                    return idx
        return None

    def fetch_and_parse_sync(self) -> list[RawMetric]:
        """Synchronous fetch and parse for scheduler jobs."""
        data = self._fetch_data_sync()
        return self.parse_response(data)

    @property
    def cached_data_age_hours(self) -> float | None:
        """Get age of cached data in hours, or None if no cache."""
        if self._cache_timestamp:
            delta = datetime.utcnow() - self._cache_timestamp
            return delta.total_seconds() / 3600
        return None
