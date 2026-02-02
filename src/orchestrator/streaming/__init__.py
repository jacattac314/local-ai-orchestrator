"""
Streaming module for real-time LLM response delivery.

Provides WebSocket and Server-Sent Events (SSE) support for:
- Real-time token streaming from LLM responses
- Bidirectional communication via WebSockets
- Connection management for multiple clients
"""

from orchestrator.streaming.manager import (
    ConnectionManager,
    StreamingClient,
    default_connection_manager,
)
from orchestrator.streaming.websocket import (
    WebSocketHandler,
    create_websocket_handler,
)
from orchestrator.streaming.sse import (
    SSEHandler,
    create_sse_response,
    format_sse_event,
)

__all__ = [
    "ConnectionManager",
    "StreamingClient",
    "WebSocketHandler",
    "SSEHandler",
    "create_websocket_handler",
    "create_sse_response",
    "format_sse_event",
    "default_connection_manager",
]
