"""
WebSocket and streaming routes for the orchestrator.

Provides real-time streaming endpoints for:
- Chat completions via WebSocket
- Connection management
- Streaming statistics
"""

import asyncio
import logging
import time
from typing import Any, AsyncIterator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from pydantic import BaseModel, Field

from orchestrator.streaming import (
    ConnectionManager,
    WebSocketHandler,
    StreamingClient,
    create_websocket_handler,
    default_connection_manager,
)
from orchestrator.streaming.websocket import StreamChunk
from orchestrator.streaming.sse import create_sse_response, mock_content_generator
from orchestrator.routing.profiles import BUILTIN_PROFILES
from orchestrator.routing.router import Router
from orchestrator.routing.scorer import CompositeScorer

logger = logging.getLogger(__name__)
router = APIRouter()


# --- WebSocket Chat Handler ---

async def chat_completion_handler(
    request: dict[str, Any],
) -> AsyncIterator[StreamChunk]:
    """
    Handle chat completion requests and yield streaming chunks.

    This is the core handler that processes chat requests
    and streams responses token by token.
    """
    from orchestrator.api.routes import get_models

    model = request.get("model", "auto")
    messages = request.get("messages", [])
    routing_profile = request.get("routing_profile", "balanced")

    # Route to best model if auto
    if model == "auto":
        profile = BUILTIN_PROFILES.get(routing_profile)
        if profile:
            scorer = CompositeScorer()
            routing_router = Router(scorer=scorer, default_profile=routing_profile)
            models = get_models()
            result = routing_router.route(models, profile)
            if result:
                model = result.selected_model.model_name

    # Generate mock streaming response
    # In production, this would call the actual LLM API
    response_text = f"[Routed to {model}] This is a streaming response. "
    response_text += "The orchestrator selected this model based on your routing profile. "
    response_text += "In production, this would stream actual tokens from the LLM API."

    words = response_text.split()
    for i, word in enumerate(words):
        content = word + (" " if i < len(words) - 1 else "")
        yield StreamChunk(
            request_id="",  # Will be set by handler
            content=content,
            model=model,
        )
        await asyncio.sleep(0.05)  # Simulate token generation delay


# Create global WebSocket handler
ws_handler = create_websocket_handler(
    chat_handler=chat_completion_handler,
    connection_manager=default_connection_manager,
)


# --- WebSocket Endpoints ---

@router.websocket("/stream")
async def websocket_stream(websocket: WebSocket):
    """
    WebSocket endpoint for streaming chat completions.

    Protocol:
    1. Connect to establish WebSocket connection
    2. Receive welcome message with client_id
    3. Send chat request:
       {
           "type": "chat",
           "model": "auto",  # or specific model
           "messages": [{"role": "user", "content": "Hello"}],
           "routing_profile": "balanced"
       }
    4. Receive streaming chunks:
       {
           "type": "chunk",
           "request_id": "...",
           "data": {"content": "...", "model": "..."}
       }
    5. Receive done event:
       {"type": "done", "request_id": "..."}

    Additional message types:
    - ping: Send {"type": "ping"} to receive {"type": "pong"}
    - cancel: Send {"type": "cancel", "request_id": "..."} to cancel
    """
    await ws_handler.handle_connection(websocket)


@router.get("/stream/stats")
async def get_streaming_stats():
    """Get streaming connection statistics."""
    stats = default_connection_manager.get_stats()
    return {
        "status": "ok",
        **stats,
    }


@router.get("/stream/clients")
async def get_streaming_clients():
    """Get list of connected streaming clients."""
    clients = default_connection_manager.get_all_clients()
    return {
        "count": len(clients),
        "clients": [c.to_dict() for c in clients],
    }


# --- SSE Streaming Endpoints ---

class SSEChatRequest(BaseModel):
    """Request for SSE chat streaming."""
    model: str = Field(default="auto", description="Model to use")
    messages: list[dict] = Field(..., description="Chat messages")
    routing_profile: str = Field(default="balanced", description="Routing profile")


@router.post("/stream/sse")
async def sse_chat_stream(request: SSEChatRequest):
    """
    Server-Sent Events endpoint for streaming chat completions.

    Alternative to WebSocket for clients that prefer SSE.
    Returns OpenAI-compatible streaming format.

    Response format:
    - event: routing (optional routing metadata)
    - data: {"id": "...", "choices": [{"delta": {"content": "..."}}]}
    - data: [DONE]
    """
    from orchestrator.api.routes import get_models

    model = request.model
    routing_info = {"profile": request.routing_profile}

    # Route if auto
    if model == "auto":
        profile = BUILTIN_PROFILES.get(request.routing_profile)
        if profile:
            scorer = CompositeScorer()
            routing_router = Router(scorer=scorer, default_profile=request.routing_profile)
            models = get_models()
            result = routing_router.route(models, profile)
            if result:
                model = result.selected_model.model_name
                routing_info = {
                    "profile": result.profile_used,
                    "selected_model": model,
                    "composite_score": result.selected_model.composite_score,
                }

    # Generate mock response
    response_text = f"[Routed to {model}] This is a streaming SSE response."

    async def content_gen() -> AsyncIterator[str]:
        async for chunk in mock_content_generator(response_text):
            yield chunk

    # Calculate prompt tokens (rough estimate)
    prompt_tokens = sum(len(str(m.get("content", "")).split()) for m in request.messages)

    return create_sse_response(
        content_generator=content_gen(),
        model=model,
        routing_info=routing_info,
        include_usage=True,
        prompt_tokens=prompt_tokens,
    )


@router.get("/stream/test")
async def test_sse_stream(
    text: str = Query(default="Hello, this is a test of the streaming endpoint."),
    delay: float = Query(default=0.1, ge=0.01, le=1.0),
):
    """
    Test SSE streaming endpoint.

    Streams the provided text word by word with configurable delay.
    Useful for testing client SSE implementations.
    """
    return create_sse_response(
        content_generator=mock_content_generator(text, delay=delay),
        model="test",
        routing_info={"profile": "test", "source": "test_endpoint"},
    )
