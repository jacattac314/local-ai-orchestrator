"""
Model data service for providing real-time model metrics.
Fetches and caches data from OpenRouter.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional

from orchestrator.adapters.openrouter import OpenRouterAdapter
from orchestrator.routing.scorer import ModelMetrics

logger = logging.getLogger(__name__)


@dataclass
class ModelDataCache:
    """Cache for model data with TTL."""
    
    models: list[ModelMetrics] = field(default_factory=list)
    custom_models: list[ModelMetrics] = field(default_factory=list)  # User-added models
    last_updated: Optional[datetime] = None
    ttl_minutes: int = 5


class ModelDataService:
    """
    Service for providing model data to the API.
    
    Fetches real data from OpenRouter and caches it.
    Falls back to mock data if fetch fails.
    Supports custom user-added models.
    """
    
    def __init__(self, cache_ttl_minutes: int = 5):
        self._cache = ModelDataCache(ttl_minutes=cache_ttl_minutes)
        self._adapter = OpenRouterAdapter()
        self._next_custom_id = 10000  # Start custom IDs high to avoid conflicts
    
    def get_models(self, force_refresh: bool = False) -> list[ModelMetrics]:
        """
        Get model metrics, using cache if available.
        Includes both OpenRouter models and custom models.
        """
        if not force_refresh and self._is_cache_valid():
            return self._cache.models + self._cache.custom_models
        
        try:
            models = self._fetch_from_openrouter()
            if models:
                self._cache.models = models
                self._cache.last_updated = datetime.utcnow()
                logger.info(f"Cached {len(models)} models from OpenRouter")
                return models + self._cache.custom_models
        except Exception as e:
            logger.error(f"Failed to fetch from OpenRouter: {e}")
        
        # Return cached data if available
        if self._cache.models:
            logger.warning("Using stale cached data")
            return self._cache.models + self._cache.custom_models
        
        # Return at least custom models
        if self._cache.custom_models:
            return self._cache.custom_models
        
        logger.warning("No model data available, returning empty list")
        return []
    
    def add_custom_model(
        self,
        model_name: str,
        cost_blended: float,
        latency_p90: Optional[float] = None,
        context_length: Optional[int] = None,
        elo_rating: Optional[float] = None,
        cost_prompt: Optional[float] = None,
        cost_completion: Optional[float] = None,
    ) -> ModelMetrics:
        """
        Add a custom model to the system.
        
        Args:
            model_name: Unique model identifier (e.g., 'ollama/llama3')
            cost_blended: Cost per million tokens (blended)
            latency_p90: P90 latency in ms (optional)
            context_length: Max context length (optional)
            elo_rating: Quality rating (optional)
            cost_prompt: Prompt cost per million (optional)
            cost_completion: Completion cost per million (optional)
            
        Returns:
            The created ModelMetrics object
        """
        # Check if model already exists
        existing = self.get_custom_model(model_name)
        if existing:
            raise ValueError(f"Model '{model_name}' already exists")
        
        model = ModelMetrics(
            model_id=self._next_custom_id,
            model_name=model_name,
            elo_rating=elo_rating,
            benchmark_average=None,
            latency_p90=latency_p90,
            ttft_p90=None,
            cost_prompt=cost_prompt,
            cost_completion=cost_completion,
            cost_blended=cost_blended,
            context_length=context_length,
        )
        
        self._cache.custom_models.append(model)
        self._next_custom_id += 1
        
        logger.info(f"Added custom model: {model_name}")
        return model
    
    def remove_custom_model(self, model_name: str) -> bool:
        """Remove a custom model by name."""
        for i, model in enumerate(self._cache.custom_models):
            if model.model_name == model_name:
                del self._cache.custom_models[i]
                logger.info(f"Removed custom model: {model_name}")
                return True
        return False
    
    def get_custom_model(self, model_name: str) -> Optional[ModelMetrics]:
        """Get a custom model by name."""
        for model in self._cache.custom_models:
            if model.model_name == model_name:
                return model
        return None
    
    def list_custom_models(self) -> list[ModelMetrics]:
        """List all custom models."""
        return self._cache.custom_models.copy()
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if not self._cache.last_updated:
            return False
        
        age = datetime.utcnow() - self._cache.last_updated
        return age < timedelta(minutes=self._cache.ttl_minutes)
    
    def _fetch_from_openrouter(self) -> list[ModelMetrics]:
        """Fetch and parse model data from OpenRouter."""
        raw_metrics = self._adapter.fetch_and_parse_sync()
        
        if not raw_metrics:
            return []
        
        # Group metrics by model name
        model_data: dict[str, dict] = {}
        
        for metric in raw_metrics:
            model_name = metric.model_name
            if model_name not in model_data:
                model_data[model_name] = {
                    "model_name": model_name,
                    "context_length": None,
                    "cost_blended": None,
                    "cost_prompt": None,
                    "cost_completion": None,
                    "latency_p90": None,
                    "ttft_p90": None,
                }
            
            # Map metrics to model data
            if metric.metric_type == "context_length":
                model_data[model_name]["context_length"] = int(metric.value)
            elif metric.metric_type == "cost_blended_per_million":
                model_data[model_name]["cost_blended"] = metric.value
            elif metric.metric_type == "cost_prompt_per_million":
                model_data[model_name]["cost_prompt"] = metric.value
            elif metric.metric_type == "cost_completion_per_million":
                model_data[model_name]["cost_completion"] = metric.value
            elif metric.metric_type == "latency_p90_ms":
                model_data[model_name]["latency_p90"] = metric.value
            elif metric.metric_type == "ttft_p90_ms":
                model_data[model_name]["ttft_p90"] = metric.value
        
        # Convert to ModelMetrics objects
        models: list[ModelMetrics] = []
        for idx, (name, data) in enumerate(model_data.items()):
            # Skip models without essential data
            if data["cost_blended"] is None:
                continue
            
            models.append(ModelMetrics(
                model_id=idx + 1,
                model_name=name,
                elo_rating=None,  # OpenRouter doesn't provide ELO
                benchmark_average=None,
                latency_p90=data["latency_p90"],
                ttft_p90=data["ttft_p90"],
                cost_prompt=data["cost_prompt"],
                cost_completion=data["cost_completion"],
                cost_blended=data["cost_blended"],
                context_length=data["context_length"],
            ))
        
        # Sort by cost (ascending) as default ordering
        models.sort(key=lambda m: m.cost_blended or float('inf'))
        
        return models
    
    def get_model_count(self) -> int:
        """Get the number of cached models."""
        return len(self._cache.models) + len(self._cache.custom_models)
    
    def get_cache_age_seconds(self) -> float:
        """Get the age of the cache in seconds."""
        if not self._cache.last_updated:
            return float('inf')
        return (datetime.utcnow() - self._cache.last_updated).total_seconds()


# Global service instance
_model_service: Optional[ModelDataService] = None


def get_model_service() -> ModelDataService:
    """Get the global model data service instance."""
    global _model_service
    if _model_service is None:
        _model_service = ModelDataService()
    return _model_service
