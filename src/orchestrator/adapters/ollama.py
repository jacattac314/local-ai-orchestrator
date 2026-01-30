"""
Ollama adapter for local LLM models.

Discovers and manages local models via the Ollama API.
Models from Ollama are free (zero cost) and run locally.
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from orchestrator.adapters.base import BenchmarkSource, RawMetric

logger = logging.getLogger(__name__)


@dataclass
class OllamaModel:
    """Represents an Ollama local model."""
    
    name: str
    model: str
    modified_at: str
    size: int  # bytes
    digest: str
    
    # Parsed metadata
    family: str = ""
    parameter_size: str = ""
    quantization: str = ""
    
    @property
    def size_gb(self) -> float:
        """Model size in gigabytes."""
        return self.size / (1024 ** 3)
    
    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        parts = [self.name]
        if self.parameter_size:
            parts.append(f"({self.parameter_size})")
        if self.quantization:
            parts.append(f"[{self.quantization}]")
        return " ".join(parts)


class OllamaAdapter(BenchmarkSource):
    """
    Adapter for Ollama local LLM service.
    
    Discovers locally installed models via Ollama's API and integrates
    them with the orchestrator's model routing system.
    
    Features:
    - Zero cost (local inference)
    - Automatic model discovery
    - Context window detection from model metadata
    - Quality estimation based on model family/size
    """
    
    def __init__(
        self,
        host: str | None = None,
        timeout: float = 10.0,
    ):
        """
        Initialize Ollama adapter.
        
        Args:
            host: Ollama API host URL (default: from OLLAMA_HOST env or localhost:11434)
            timeout: Request timeout in seconds
        """
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)
        self._models_cache: list[OllamaModel] = []
        self._last_sync: datetime | None = None
        
    @property
    def source_name(self) -> str:
        return "ollama"
    
    @property
    def sync_interval_minutes(self) -> int:
        return 5  # Check for new local models every 5 minutes
    
    @property
    def is_available(self) -> bool:
        """Check if Ollama is running and accessible."""
        return self._last_sync is not None
    
    async def check_connection(self) -> bool:
        """Test connection to Ollama API."""
        try:
            response = await self._client.get(f"{self.host}/api/version")
            return response.status_code == 200
        except Exception:
            return False
    
    async def fetch_data(self) -> dict[str, Any]:
        """
        Fetch list of models from Ollama.
        
        Returns:
            Raw response from /api/tags endpoint
            
        Raises:
            httpx.HTTPError: On connection failure
        """
        try:
            response = await self._client.get(f"{self.host}/api/tags")
            response.raise_for_status()
            self._last_sync = datetime.utcnow()
            return response.json()
        except httpx.ConnectError:
            logger.warning(f"Ollama not available at {self.host}")
            return {"models": []}
        except Exception as e:
            logger.error(f"Error fetching Ollama models: {e}")
            return {"models": []}
    
    def parse_response(self, data: dict[str, Any]) -> list[RawMetric]:
        """
        Parse Ollama models response into RawMetric objects.
        
        Creates quality, latency, and cost metrics for each model.
        Local models have zero cost and typically faster cold-start latency.
        """
        metrics: list[RawMetric] = []
        models = data.get("models", [])
        
        self._models_cache = []
        
        for model_data in models:
            model = self._parse_model(model_data)
            self._models_cache.append(model)
            
            # Estimate quality score based on model family and size
            quality_score = self._estimate_quality(model)
            
            # Estimate context window (default 4096, larger for some models)
            context_window = self._estimate_context_window(model)
            
            # Create metrics
            metrics.extend([
                RawMetric(
                    model_name=model.name,
                    metric_type="quality_score",
                    value=quality_score,
                    source=self.source_name,
                    metadata={
                        "family": model.family,
                        "parameter_size": model.parameter_size,
                        "quantization": model.quantization,
                        "size_gb": model.size_gb,
                        "is_local": True,
                    }
                ),
                RawMetric(
                    model_name=model.name,
                    metric_type="context_window",
                    value=context_window,
                    source=self.source_name,
                ),
                RawMetric(
                    model_name=model.name,
                    metric_type="cost_per_million_input",
                    value=0.0,  # Free - local inference
                    source=self.source_name,
                ),
                RawMetric(
                    model_name=model.name,
                    metric_type="cost_per_million_output", 
                    value=0.0,  # Free - local inference
                    source=self.source_name,
                ),
                # Local models typically have better latency (no network)
                RawMetric(
                    model_name=model.name,
                    metric_type="latency_p50",
                    value=50.0,  # Estimated 50ms for local inference
                    source=self.source_name,
                    metadata={"estimated": True}
                ),
            ])
        
        logger.info(f"Discovered {len(self._models_cache)} Ollama models")
        return metrics
    
    def _parse_model(self, data: dict[str, Any]) -> OllamaModel:
        """Parse raw model data into OllamaModel."""
        name = data.get("name", "unknown")
        
        # Parse details if available
        details = data.get("details", {})
        family = details.get("family", "")
        parameter_size = details.get("parameter_size", "")
        quantization = details.get("quantization_level", "")
        
        return OllamaModel(
            name=name,
            model=data.get("model", name),
            modified_at=data.get("modified_at", ""),
            size=data.get("size", 0),
            digest=data.get("digest", ""),
            family=family,
            parameter_size=parameter_size,
            quantization=quantization,
        )
    
    def _estimate_quality(self, model: OllamaModel) -> float:
        """
        Estimate quality score for a local model.
        
        Uses heuristics based on model family and parameter count.
        Scale: 0-100 to match other sources.
        """
        base_score = 50.0  # Default for unknown models
        
        # Family-based scoring
        family_scores = {
            "llama": 75.0,
            "qwen": 78.0,
            "phi": 72.0,
            "gemma": 73.0,
            "mistral": 76.0,
            "mixtral": 82.0,
            "codellama": 74.0,
            "deepseek": 77.0,
            "yi": 71.0,
        }
        
        family_lower = model.family.lower() if model.family else ""
        for family, score in family_scores.items():
            if family in family_lower or family in model.name.lower():
                base_score = score
                break
        
        # Adjust for parameter size
        param_size = model.parameter_size.lower()
        if "70b" in param_size or "72b" in param_size:
            base_score += 10
        elif "34b" in param_size or "32b" in param_size:
            base_score += 7
        elif "13b" in param_size or "14b" in param_size:
            base_score += 4
        elif "7b" in param_size or "8b" in param_size:
            base_score += 2
        elif "3b" in param_size or "4b" in param_size:
            base_score -= 2
        elif "1b" in param_size or "2b" in param_size:
            base_score -= 5
        
        # Quantization penalty (lower precision = slightly lower quality)
        quant = model.quantization.lower()
        if "q4" in quant or "q3" in quant:
            base_score -= 3
        elif "q5" in quant:
            base_score -= 2
        elif "q6" in quant or "q8" in quant:
            base_score -= 1
        
        return min(max(base_score, 0.0), 100.0)
    
    def _estimate_context_window(self, model: OllamaModel) -> int:
        """Estimate context window size based on model family."""
        # Known context windows for common model families
        context_windows = {
            "llama": 8192,
            "qwen": 32768,
            "phi": 4096,
            "gemma": 8192,
            "mistral": 32768,
            "mixtral": 32768,
            "deepseek": 16384,
        }
        
        family_lower = model.family.lower() if model.family else ""
        for family, window in context_windows.items():
            if family in family_lower or family in model.name.lower():
                return window
        
        return 4096  # Conservative default
    
    def get_cached_models(self) -> list[OllamaModel]:
        """Get cached list of discovered models."""
        return self._models_cache.copy()
    
    async def pull_model(self, model_name: str) -> dict[str, Any]:
        """
        Pull a model from Ollama registry.
        
        Args:
            model_name: Name of model to pull (e.g., "llama3.2")
            
        Returns:
            Status response from Ollama
        """
        try:
            response = await self._client.post(
                f"{self.host}/api/pull",
                json={"name": model_name},
                timeout=None,  # Pulling can take a long time
            )
            return response.json()
        except Exception as e:
            logger.error(f"Error pulling model {model_name}: {e}")
            return {"error": str(e)}
    
    async def generate(
        self,
        model: str,
        prompt: str,
        **kwargs
    ) -> dict[str, Any]:
        """
        Generate completion using Ollama.
        
        Args:
            model: Model name to use
            prompt: Input prompt
            **kwargs: Additional generation parameters
            
        Returns:
            Generation response
        """
        try:
            response = await self._client.post(
                f"{self.host}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    **kwargs
                },
                timeout=120.0,  # Long timeout for generation
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Generation error: {e}")
            return {"error": str(e)}
    
    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        **kwargs
    ) -> dict[str, Any]:
        """
        Chat completion using Ollama (OpenAI-compatible format).
        
        Args:
            model: Model name to use
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional generation parameters
            
        Returns:
            Chat completion response
        """
        try:
            response = await self._client.post(
                f"{self.host}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    **kwargs
                },
                timeout=120.0,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return {"error": str(e)}
    
    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()


# Default instance for import convenience
default_ollama_adapter = OllamaAdapter()
