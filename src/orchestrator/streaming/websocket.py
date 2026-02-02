"""
WebSocket handler for streaming LLM responses.

Provides bidirectional communication for real-time
token streaming and chat interactions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Coroutine

from fastapi import WebSocket, WebSocketDisconnect

from orchestrator.streaming.manager import (
    ConnectionManager,
    ConnectionState,
    StreamingClient,
    default_connection_manager,
)

logger = logging.getLogger(__name__)


@dataclass
class StreamChunk:
    """A chunk of streaming response."""

    request_id: str
    content: str
    model: str
    index: int = 0
    finish_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": "chunk",
            "request_id": self.request_id,
            "data": {
                "content": self.content,
                "model": self.model,
                "index": self.index,
                "finish_reason": self.finish_reason,
            },
            "metadata": self.metadata,
        }


@dataclass
class StreamEvent:
    """An event in the streaming lifecycle."""

    type: str  # start, chunk, done, error
    request_id: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.type,
            "request_id": self.request_id,
            "data": self.data,
            "timestamp": self.timestamp,
        }


class WebSocketHandler:
    """
    Handles WebSocket connections for streaming chat completions.

    Supports:
    - Chat completion requests via WebSocket
    - Real-time token streaming
    - Request cancellation
    - Connection multiplexing
    """

    def __init__(
        self,
        connection_manager: ConnectionManager | None = None,
        chat_handler: Callable[
            [dict[str, Any]], AsyncIterator[StreamChunk]
        ] | None = None,
    ) -> None:
        """
        Initialize WebSocket handler.

        Args:
            connection_manager: Connection manager instance
            chat_handler: Async generator function that yields stream chunks
        """
        self.manager = connection_manager or default_connection_manager
        self._chat_handler = chat_handler
        self._active_streams: dict[str, asyncio.Task] = {}
        self._cancelled_requests: set[str] = set()

    def set_chat_handler(
        self,
        handler: Callable[[dict[str, Any]], AsyncIterator[StreamChunk]],
    ) -> None:
        """Set the chat handler function."""
        self._chat_handler = handler

    async def handle_connection(self, websocket: WebSocket) -> None:
        """
        Handle a WebSocket connection lifecycle.

        Args:
            websocket: The WebSocket connection
        """
        client = await self.manager.connect(websocket)
        if not client:
            return

        try:
            await self._send_welcome(client)
            await self._message_loop(client)
        except WebSocketDisconnect:
            logger.info(f"Client {client.client_id} disconnected")
        except Exception as e:
            logger.error(f"Error handling WebSocket: {e}")
            await self._send_error(client, str(e))
        finally:
            await self._cleanup_client(client)
            await self.manager.disconnect(client.client_id)

    async def _send_welcome(self, client: StreamingClient) -> None:
        """Send welcome message to new client."""
        await self.manager.send_to_client(
            client.client_id,
            {
                "type": "connected",
                "client_id": client.client_id,
                "message": "Connected to streaming endpoint",
            },
        )

    async def _message_loop(self, client: StreamingClient) -> None:
        """Process incoming messages from client."""
        while True:
            try:
                data = await client.websocket.receive_json()
                await self._handle_message(client, data)
            except json.JSONDecodeError as e:
                await self._send_error(client, f"Invalid JSON: {e}")
            except WebSocketDisconnect:
                raise
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                await self._send_error(client, str(e))

    async def _handle_message(
        self,
        client: StreamingClient,
        message: dict[str, Any],
    ) -> None:
        """
        Handle an incoming message from client.

        Message types:
        - chat: Start a chat completion request
        - cancel: Cancel an ongoing request
        - ping: Respond with pong
        """
        msg_type = message.get("type", "chat")

        if msg_type == "ping":
            await self.manager.send_to_client(
                client.client_id,
                {"type": "pong", "timestamp": time.time()},
            )

        elif msg_type == "cancel":
            request_id = message.get("request_id")
            if request_id:
                await self._cancel_request(client, request_id)

        elif msg_type == "chat":
            await self._handle_chat_request(client, message)

        else:
            await self._send_error(
                client,
                f"Unknown message type: {msg_type}",
            )

    async def _handle_chat_request(
        self,
        client: StreamingClient,
        message: dict[str, Any],
    ) -> None:
        """Handle a chat completion request."""
        if not self._chat_handler:
            await self._send_error(
                client,
                "Chat handler not configured",
            )
            return

        request_id = message.get("request_id") or str(uuid.uuid4())

        # Send start event
        await self._send_event(
            client,
            StreamEvent(
                type="start",
                request_id=request_id,
                data={
                    "model": message.get("model", "auto"),
                    "messages_count": len(message.get("messages", [])),
                },
            ),
        )

        # Subscribe client to this request
        self.manager.subscribe_to_request(client.client_id, request_id)

        # Start streaming in background task
        task = asyncio.create_task(
            self._stream_response(client, request_id, message)
        )
        self._active_streams[request_id] = task

    async def _stream_response(
        self,
        client: StreamingClient,
        request_id: str,
        message: dict[str, Any],
    ) -> None:
        """Stream response chunks to client."""
        try:
            chunk_count = 0
            total_content = ""

            async for chunk in self._chat_handler(message):
                # Check if cancelled
                if request_id in self._cancelled_requests:
                    self._cancelled_requests.discard(request_id)
                    await self._send_event(
                        client,
                        StreamEvent(
                            type="cancelled",
                            request_id=request_id,
                            data={"chunks_sent": chunk_count},
                        ),
                    )
                    return

                # Send chunk
                chunk.request_id = request_id
                chunk.index = chunk_count
                await self.manager.send_to_client(
                    client.client_id,
                    chunk.to_dict(),
                )
                chunk_count += 1
                total_content += chunk.content

            # Send done event
            await self._send_event(
                client,
                StreamEvent(
                    type="done",
                    request_id=request_id,
                    data={
                        "total_chunks": chunk_count,
                        "total_length": len(total_content),
                    },
                ),
            )

        except Exception as e:
            logger.error(f"Error streaming response: {e}")
            await self._send_event(
                client,
                StreamEvent(
                    type="error",
                    request_id=request_id,
                    data={"error": str(e)},
                ),
            )

        finally:
            # Cleanup
            self._active_streams.pop(request_id, None)
            self.manager.unsubscribe_from_request(client.client_id, request_id)

    async def _cancel_request(
        self,
        client: StreamingClient,
        request_id: str,
    ) -> None:
        """Cancel an ongoing request."""
        if request_id in self._active_streams:
            self._cancelled_requests.add(request_id)
            task = self._active_streams.get(request_id)
            if task and not task.done():
                # Let the stream loop handle cancellation gracefully
                pass

            await self.manager.send_to_client(
                client.client_id,
                {
                    "type": "cancel_acknowledged",
                    "request_id": request_id,
                },
            )
        else:
            await self._send_error(
                client,
                f"No active request with ID: {request_id}",
            )

    async def _send_event(
        self,
        client: StreamingClient,
        event: StreamEvent,
    ) -> None:
        """Send a stream event to client."""
        await self.manager.send_to_client(
            client.client_id,
            event.to_dict(),
        )

    async def _send_error(
        self,
        client: StreamingClient,
        error: str,
    ) -> None:
        """Send an error message to client."""
        await self.manager.send_to_client(
            client.client_id,
            {
                "type": "error",
                "error": error,
                "timestamp": time.time(),
            },
        )

    async def _cleanup_client(self, client: StreamingClient) -> None:
        """Cleanup when client disconnects."""
        # Cancel any active streams for this client
        if client.current_request_id:
            request_id = client.current_request_id
            if request_id in self._active_streams:
                self._cancelled_requests.add(request_id)


def create_websocket_handler(
    chat_handler: Callable[[dict[str, Any]], AsyncIterator[StreamChunk]] | None = None,
    connection_manager: ConnectionManager | None = None,
) -> WebSocketHandler:
    """
    Factory function to create a WebSocket handler.

    Args:
        chat_handler: Async generator that yields StreamChunk objects
        connection_manager: Connection manager instance

    Returns:
        Configured WebSocketHandler
    """
    return WebSocketHandler(
        connection_manager=connection_manager,
        chat_handler=chat_handler,
    )
