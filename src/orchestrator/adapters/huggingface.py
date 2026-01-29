"""HuggingFace Open LLM Leaderboard adapter for benchmark scores."""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from orchestrator.adapters.base import BenchmarkSource, RawMetric
from orchestrator.http.client import SyncHttpClient

logger = logging.getLogger(__name__)


class HuggingFaceAdapter(BenchmarkSource):
    """
    Adapter for HuggingFace Open LLM Leaderboard.

    Fetches benchmark scores including:
    - MMLU-Pro (Multi-task Language Understanding)
    - IFEval (Instruction Following)
    - BigBench-Hard (Challenging reasoning tasks)
    - GPQA (Graduate-level Q&A)
    - MATH (Mathematical reasoning)
    - MuSR (Multi-step reasoning)

    Supports differential downloads by tracking commit SHA.
    """

    # HuggingFace dataset endpoints
    LEADERBOARD_API = "https://huggingface.co/api/datasets/open-llm-leaderboard/results"
    RESULTS_URL = "https://huggingface.co/datasets/open-llm-leaderboard/results/resolve/main/latest_results.json"
    
    # Alternative: Individual model results
    MODEL_RESULTS_PATTERN = "https://huggingface.co/datasets/open-llm-leaderboard/results/resolve/main/{model_id}/results.json"

    # Cache directory for differential downloads
    CACHE_DIR = Path("data/hf_cache")

    def __init__(self, cache_dir: Path | None = None) -> None:
        """
        Initialize the HuggingFace adapter.

        Args:
            cache_dir: Directory for caching downloaded data
        """
        self._cache_dir = cache_dir or self.CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_commit_sha: str | None = None

    @property
    def source_name(self) -> str:
        return "huggingface"

    @property
    def sync_interval_minutes(self) -> int:
        return 1440  # 24 hours

    async def fetch_data(self) -> dict[str, Any]:
        """Fetch data from HuggingFace (async wrapper)."""
        return self._fetch_data_sync()

    def _fetch_data_sync(self) -> dict[str, Any]:
        """
        Fetch benchmark data from HuggingFace.

        Uses differential download by checking commit SHA.
        """
        client = SyncHttpClient()

        try:
            # Check for updates via API
            logger.info("Checking HuggingFace leaderboard for updates...")
            
            # Try to get the latest results
            response = client.get(self.RESULTS_URL)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if data has changed
                content_hash = self._compute_hash(response.text)
                if content_hash == self._last_commit_sha:
                    logger.info("HuggingFace data unchanged (same hash)")
                    # Return cached if available
                    cached = self._load_cache()
                    if cached:
                        return cached
                
                self._last_commit_sha = content_hash
                result = {"format": "json", "data": data, "hash": content_hash}
                self._save_cache(result)
                return result
            
            # Fallback: Try API endpoint
            logger.info("Direct results failed, trying API endpoint...")
            response = client.get(self.LEADERBOARD_API)
            
            if response.status_code == 200:
                data = response.json()
                result = {"format": "api", "data": data}
                return result

            # Use cache if available
            cached = self._load_cache()
            if cached:
                logger.info("Using cached HuggingFace data")
                return cached

            raise RuntimeError(f"Failed to fetch HuggingFace data: {response.status_code}")

        finally:
            client.close()

    def _compute_hash(self, content: str) -> str:
        """Compute SHA256 hash of content for differential downloads."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _save_cache(self, data: dict[str, Any]) -> None:
        """Save data to cache file."""
        cache_file = self._cache_dir / "leaderboard_cache.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(data, f)
            logger.debug(f"Saved cache to {cache_file}")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def _load_cache(self) -> dict[str, Any] | None:
        """Load data from cache file."""
        cache_file = self._cache_dir / "leaderboard_cache.json"
        try:
            if cache_file.exists():
                with open(cache_file) as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
        return None

    def validate_response(self, data: dict[str, Any]) -> bool:
        """Validate the response structure."""
        if not isinstance(data, dict):
            return False
        if "format" not in data or "data" not in data:
            return False
        return True

    def parse_response(self, data: dict[str, Any]) -> list[RawMetric]:
        """Parse HuggingFace response into RawMetric objects."""
        if not self.validate_response(data):
            logger.error("Invalid HuggingFace response structure")
            return []

        raw_data = data["data"]
        
        if data["format"] == "json":
            return self._parse_results_json(raw_data)
        elif data["format"] == "api":
            return self._parse_api_response(raw_data)
        
        return []

    def _parse_results_json(self, data: Any) -> list[RawMetric]:
        """
        Parse the latest_results.json format.

        This typically contains a list of model results with benchmark scores.
        """
        metrics: list[RawMetric] = []
        timestamp = datetime.utcnow()

        # Handle different possible structures
        if isinstance(data, dict):
            models = data.get("models", data.get("results", [data]))
        elif isinstance(data, list):
            models = data
        else:
            logger.warning(f"Unexpected data type: {type(data)}")
            return []

        for model_data in models:
            if not isinstance(model_data, dict):
                continue

            # Get model name
            model_name = model_data.get("model", model_data.get("model_name", model_data.get("name")))
            if not model_name:
                continue

            # Parse benchmark scores
            model_metrics = self._extract_benchmark_scores(model_name, model_data, timestamp)
            metrics.extend(model_metrics)

        logger.info(f"Parsed {len(metrics)} metrics from HuggingFace JSON")
        return metrics

    def _parse_api_response(self, data: Any) -> list[RawMetric]:
        """Parse the API response format."""
        # API response structure may differ
        return self._parse_results_json(data)

    def _extract_benchmark_scores(
        self, 
        model_name: str, 
        model_data: dict[str, Any], 
        timestamp: datetime
    ) -> list[RawMetric]:
        """
        Extract benchmark scores from model data.

        Normalizes scores to 0-100 scale where needed.
        """
        metrics: list[RawMetric] = []

        # Benchmark mappings: (possible keys, metric name, needs normalization to 100)
        benchmarks = [
            (["mmlu_pro", "mmlu-pro", "MMLU-Pro", "mmlu"], "mmlu_pro", False),
            (["ifeval", "IFEval", "if_eval"], "ifeval", False),
            (["bbh", "bigbench_hard", "BigBench-Hard", "bbh_fewshot"], "bbh", False),
            (["gpqa", "GPQA", "gpqa_main"], "gpqa", False),
            (["math", "MATH", "math_hard", "math_lvl5"], "math", False),
            (["musr", "MuSR", "multi_step_reasoning"], "musr", False),
            (["arc_challenge", "arc", "ARC-C"], "arc", False),
            (["hellaswag", "HellaSwag"], "hellaswag", False),
            (["winogrande", "WinoGrande"], "winogrande", False),
            (["truthfulqa", "TruthfulQA", "truthfulqa_mc2"], "truthfulqa", False),
        ]

        # Also look for nested results
        results = model_data.get("results", model_data)
        
        for possible_keys, metric_name, needs_norm in benchmarks:
            value = None
            
            for key in possible_keys:
                # Try direct key
                if key in results:
                    value = results[key]
                    break
                # Try nested in results
                if key in model_data:
                    value = model_data[key]
                    break
                # Try lowercase
                for k, v in results.items():
                    if k.lower() == key.lower():
                        value = v
                        break

            if value is not None:
                try:
                    # Handle nested score objects
                    if isinstance(value, dict):
                        value = value.get("acc", value.get("score", value.get("accuracy")))
                    
                    if value is None:
                        continue

                    score = float(value)
                    
                    # Normalize to 0-100 if needed (some scores are 0-1)
                    if score <= 1.0:
                        score *= 100

                    metrics.append(
                        RawMetric(
                            model_name=model_name,
                            metric_type=f"benchmark_{metric_name}",
                            value=score,
                            source=self.source_name,
                            timestamp=timestamp,
                            metadata={"benchmark": metric_name, "raw_value": value},
                        )
                    )
                except (ValueError, TypeError) as e:
                    logger.debug(f"Could not parse {metric_name} for {model_name}: {e}")

        # Calculate average score if we have multiple benchmarks
        if len(metrics) >= 3:
            avg_score = sum(m.value for m in metrics) / len(metrics)
            metrics.append(
                RawMetric(
                    model_name=model_name,
                    metric_type="benchmark_average",
                    value=avg_score,
                    source=self.source_name,
                    timestamp=timestamp,
                    metadata={"num_benchmarks": len(metrics)},
                )
            )

        return metrics

    def fetch_and_parse_sync(self) -> list[RawMetric]:
        """Synchronous fetch and parse for scheduler jobs."""
        data = self._fetch_data_sync()
        return self.parse_response(data)
