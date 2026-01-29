"""API routes for the orchestrator."""

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from orchestrator.routing.profiles import BUILTIN_PROFILES, RoutingProfile
from orchestrator.routing.scorer import CompositeScorer, ModelMetrics, ModelScore
from orchestrator.routing.router import Router

logger = logging.getLogger(__name__)
router = APIRouter()


# Import model service for real data
from orchestrator.api.model_service import get_model_service


def get_models() -> list:
    """Get model data - uses real OpenRouter data with cache."""
    service = get_model_service()
    models = service.get_models()
    if models:
        return models
    # Fallback to mock data if service fails
    return get_mock_models()


# --- Request/Response Models ---

class Message(BaseModel):
    """Chat message."""
    role: str = Field(..., description="Message role: system, user, assistant")
    content: str = Field(..., description="Message content")


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    
    model: str = Field(
        default="auto",
        description="Model to use, or 'auto' for automatic selection",
    )
    messages: list[Message] = Field(..., description="List of messages")
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int | None = Field(default=None, description="Max tokens to generate")
    stream: bool = Field(default=False, description="Stream response")
    
    # Orchestrator-specific
    routing_profile: str = Field(
        default="balanced",
        description="Routing profile: quality, balanced, speed, budget",
    )


class ChatChoice(BaseModel):
    """Chat completion choice."""
    index: int = 0
    message: Message
    finish_reason: str = "stop"


class Usage(BaseModel):
    """Token usage stats."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""
    id: str = "chatcmpl-local"
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]
    usage: Usage
    
    # Orchestrator metadata
    routing_info: dict[str, Any] | None = None


class ModelRankingItem(BaseModel):
    """Ranked model with scores."""
    rank: int
    model_id: int
    model_name: str
    composite_score: float
    quality_score: float
    latency_score: float
    cost_score: float
    meets_constraints: bool


class ModelRankingsResponse(BaseModel):
    """Model rankings response."""
    profile: str
    rankings: list[ModelRankingItem]
    total_models: int


class RoutingProfileInfo(BaseModel):
    """Routing profile information."""
    name: str
    description: str
    quality_weight: float
    latency_weight: float
    cost_weight: float
    context_weight: float


# --- Mock data for demo ---

def get_mock_models() -> list[ModelMetrics]:
    """Get mock model data for demonstration."""
    return [
        ModelMetrics(
            model_id=1,
            model_name="gpt-4-turbo",
            elo_rating=1290,
            latency_p90=850,
            cost_blended=15.0,
            context_length=128000,
        ),
        ModelMetrics(
            model_id=2,
            model_name="gpt-4o",
            elo_rating=1310,
            latency_p90=450,
            cost_blended=7.5,
            context_length=128000,
        ),
        ModelMetrics(
            model_id=3,
            model_name="claude-3-opus",
            elo_rating=1285,
            latency_p90=1200,
            cost_blended=45.0,
            context_length=200000,
        ),
        ModelMetrics(
            model_id=4,
            model_name="claude-3.5-sonnet",
            elo_rating=1275,
            latency_p90=500,
            cost_blended=9.0,
            context_length=200000,
        ),
        ModelMetrics(
            model_id=5,
            model_name="gemini-1.5-pro",
            elo_rating=1260,
            latency_p90=600,
            cost_blended=3.5,
            context_length=1000000,
        ),
        ModelMetrics(
            model_id=6,
            model_name="llama-3-70b",
            elo_rating=1220,
            latency_p90=400,
            cost_blended=0.9,
            context_length=8192,
        ),
        ModelMetrics(
            model_id=7,
            model_name="mixtral-8x22b",
            elo_rating=1200,
            latency_p90=350,
            cost_blended=1.2,
            context_length=65536,
        ),
    ]


# --- Endpoints ---

@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def create_chat_completion(request: ChatCompletionRequest):
    """
    OpenAI-compatible chat completion endpoint.
    
    When model is 'auto', uses the routing engine to select the best model.
    """
    start_time = time.time()
    
    # Get routing profile
    profile = BUILTIN_PROFILES.get(request.routing_profile)
    if not profile:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown profile: {request.routing_profile}",
        )
    
    # Route to best model
    scorer = CompositeScorer()
    routing_router = Router(scorer=scorer, default_profile=request.routing_profile)
    models = get_models()  # Uses real OpenRouter data
    
    if request.model == "auto":
        result = routing_router.route(models, profile)
        if not result:
            raise HTTPException(status_code=503, detail="No available models")
        selected_model = result.selected_model.model_name
        routing_info = {
            "profile": result.profile_used,
            "selected_model": result.selected_model.model_name,
            "composite_score": result.selected_model.composite_score,
            "routing_time_ms": result.routing_time_ms,
            "fallbacks": [m.model_name for m in result.fallback_models],
        }
    else:
        selected_model = request.model
        routing_info = {"profile": "manual", "selected_model": request.model}
    
    # Stream response if requested
    if request.stream:
        return StreamingResponse(
            stream_response(selected_model, request.messages, routing_info),
            media_type="text/event-stream",
        )
    
    # Mock response (in production, would call actual model API)
    response_content = f"[Routed to {selected_model}] This is a mock response. In production, this would call the actual model API."
    
    return ChatCompletionResponse(
        created=int(start_time),
        model=selected_model,
        choices=[
            ChatChoice(
                message=Message(role="assistant", content=response_content),
            )
        ],
        usage=Usage(
            prompt_tokens=sum(len(m.content.split()) for m in request.messages),
            completion_tokens=len(response_content.split()),
            total_tokens=sum(len(m.content.split()) for m in request.messages) + len(response_content.split()),
        ),
        routing_info=routing_info,
    )


async def stream_response(
    model: str,
    messages: list[Message],
    routing_info: dict[str, Any],
) -> AsyncIterator[str]:
    """Stream chat completion response in SSE format."""
    # Send routing info first
    yield f"data: {json.dumps({'routing_info': routing_info})}\n\n"
    
    # Mock streaming response
    response_text = f"[Routed to {model}] This is a streamed mock response."
    
    for word in response_text.split():
        chunk = {
            "id": "chatcmpl-stream",
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": word + " "},
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        await asyncio.sleep(0.05)
    
    # Final chunk
    final = {
        "id": "chatcmpl-stream",
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(final)}\n\n"
    yield "data: [DONE]\n\n"


@router.get("/models/rankings", response_model=ModelRankingsResponse)
async def get_model_rankings(
    profile: str = Query(default="balanced", description="Routing profile to use"),
    limit: int = Query(default=10, ge=1, le=50),
):
    """Get model rankings for a routing profile."""
    routing_profile = BUILTIN_PROFILES.get(profile)
    if not routing_profile:
        raise HTTPException(status_code=400, detail=f"Unknown profile: {profile}")
    
    scorer = CompositeScorer()
    models = get_models()  # Uses real OpenRouter data
    ranked = scorer.rank_models(models, routing_profile, limit=limit)
    
    rankings = [
        ModelRankingItem(
            rank=idx + 1,
            model_id=score.model_id,
            model_name=score.model_name,
            composite_score=round(score.composite_score, 4),
            quality_score=round(score.quality_score, 4),
            latency_score=round(score.latency_score, 4),
            cost_score=round(score.cost_score, 4),
            meets_constraints=score.meets_constraints,
        )
        for idx, score in enumerate(ranked)
    ]
    
    return ModelRankingsResponse(
        profile=profile,
        rankings=rankings,
        total_models=len(models),
    )


@router.get("/routing/profiles", response_model=list[RoutingProfileInfo])
async def get_routing_profiles():
    """Get available routing profiles."""
    return [
        RoutingProfileInfo(
            name=p.name,
            description=p.description,
            quality_weight=p.quality_weight,
            latency_weight=p.latency_weight,
            cost_weight=p.cost_weight,
            context_weight=p.context_weight,
        )
        for p in BUILTIN_PROFILES.values()
    ]


@router.get("/models")
async def list_models():
    """List available models."""
    models = get_models()  # Uses real OpenRouter data
    return {
        "object": "list",
        "data": [
            {
                "id": m.model_name,
                "object": "model",
                "owned_by": "orchestrator",
            }
            for m in models
        ],
    }


@router.get("/routing_profiles")
async def get_routing_profiles_dict():
    """Get routing profiles as a dictionary (for frontend compatibility)."""
    profiles = {}
    for name, profile in BUILTIN_PROFILES.items():
        profiles[name] = {
            "quality_weight": profile.quality_weight,
            "latency_weight": profile.latency_weight,
            "cost_weight": profile.cost_weight,
            "context_weight": profile.context_weight,
        }
        if profile.min_quality:
            profiles[name]["min_quality"] = profile.min_quality
        if profile.max_latency_ms:
            profiles[name]["max_latency_ms"] = profile.max_latency_ms
        if profile.max_cost_per_million:
            profiles[name]["max_cost_per_million"] = profile.max_cost_per_million
    
    return {"profiles": profiles}


# --- Analytics Endpoints ---

@router.get("/analytics/summary")
async def get_analytics_summary(
    period: str = Query(default="24h", description="Time period: 1h, 24h, 7d, 30d"),
):
    """Get analytics summary for the specified period."""
    from orchestrator.analytics import default_collector
    
    # Parse period to hours
    period_hours = {
        "1h": 1,
        "24h": 24,
        "7d": 24 * 7,
        "30d": 24 * 30,
    }.get(period, 24)
    
    summary = default_collector.get_summary(period_hours)
    return summary


@router.get("/analytics/usage")
async def get_analytics_usage(
    period: str = Query(default="24h", description="Time period"),
    bucket: int = Query(default=60, ge=5, le=1440, description="Bucket size in minutes"),
):
    """Get time-series usage data."""
    from orchestrator.analytics import default_collector
    
    period_hours = {
        "1h": 1,
        "24h": 24,
        "7d": 24 * 7,
        "30d": 24 * 30,
    }.get(period, 24)
    
    return {
        "period": period,
        "bucket_minutes": bucket,
        "data": default_collector.get_usage_timeseries(period_hours, bucket),
    }


@router.get("/analytics/models")
async def get_analytics_models(
    period: str = Query(default="24h", description="Time period"),
):
    """Get per-model usage breakdown."""
    from orchestrator.analytics import default_collector
    
    period_hours = {
        "1h": 1,
        "24h": 24,
        "7d": 24 * 7,
        "30d": 24 * 30,
    }.get(period, 24)
    
    return {
        "period": period,
        "models": default_collector.get_model_breakdown(period_hours),
    }

