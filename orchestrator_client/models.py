"""
Pydantic models for Orchestrator API responses.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ModelRanking:
    """A ranked model with scores."""
    
    model_id: int
    model_name: str
    composite_score: float
    quality_score: float
    latency_score: float
    cost_score: float
    
    @classmethod
    def from_dict(cls, data: dict) -> "ModelRanking":
        return cls(
            model_id=data.get("model_id", 0),
            model_name=data.get("model_name", ""),
            composite_score=data.get("composite_score", 0.0),
            quality_score=data.get("quality_score", 0.0),
            latency_score=data.get("latency_score", 0.0),
            cost_score=data.get("cost_score", 0.0),
        )


@dataclass
class RoutingResult:
    """Result of a routing decision."""
    
    selected_model: str
    fallback_models: list[str]
    profile_used: str
    routing_time_ms: float
    
    @classmethod
    def from_dict(cls, data: dict) -> "RoutingResult":
        return cls(
            selected_model=data.get("selected_model", {}).get("model_name", ""),
            fallback_models=[m.get("model_name", "") for m in data.get("fallback_models", [])],
            profile_used=data.get("profile_used", "balanced"),
            routing_time_ms=data.get("routing_time_ms", 0.0),
        )


@dataclass
class RoutingProfile:
    """A routing profile configuration."""
    
    name: str
    quality_weight: float
    latency_weight: float
    cost_weight: float
    min_quality: Optional[float] = None
    max_latency_ms: Optional[float] = None
    max_cost_per_million: Optional[float] = None
    
    @classmethod
    def from_dict(cls, name: str, data: dict) -> "RoutingProfile":
        return cls(
            name=name,
            quality_weight=data.get("quality_weight", 0.0),
            latency_weight=data.get("latency_weight", 0.0),
            cost_weight=data.get("cost_weight", 0.0),
            min_quality=data.get("min_quality"),
            max_latency_ms=data.get("max_latency_ms"),
            max_cost_per_million=data.get("max_cost_per_million"),
        )


@dataclass
class AnalyticsSummary:
    """Analytics summary data."""
    
    total_requests: int
    total_tokens: int
    estimated_cost: float
    avg_latency_ms: float
    top_models: list[dict]
    requests_by_profile: dict[str, int]
    
    @classmethod
    def from_dict(cls, data: dict) -> "AnalyticsSummary":
        return cls(
            total_requests=data.get("total_requests", 0),
            total_tokens=data.get("total_tokens", 0),
            estimated_cost=data.get("estimated_cost", 0.0),
            avg_latency_ms=data.get("avg_latency_ms", 0.0),
            top_models=data.get("top_models", []),
            requests_by_profile=data.get("requests_by_profile", {}),
        )


@dataclass 
class ChatMessage:
    """A chat message."""
    
    role: str
    content: str
    
    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class ChatCompletion:
    """A chat completion response."""
    
    id: str
    model: str
    content: str
    finish_reason: str
    usage: dict
    
    @classmethod
    def from_dict(cls, data: dict) -> "ChatCompletion":
        choices = data.get("choices", [{}])
        message = choices[0].get("message", {}) if choices else {}
        return cls(
            id=data.get("id", ""),
            model=data.get("model", ""),
            content=message.get("content", ""),
            finish_reason=choices[0].get("finish_reason", "") if choices else "",
            usage=data.get("usage", {}),
        )
