"""
Connection manager for WebSocket streaming.

Handles multiple client connections, message broadcasting,
and connection lifecycle management.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionState(str, Enum):
    """WebSocket connection states."""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    STREAMING = "streaming"
    CLOSING = "closing"
    CLOSED = "closed"


@dataclass
class StreamingClient:
    """Represents a connected streaming client."""

    client_id: str
    websocket: WebSocket
    connected_at: float = field(default_factory=time.time)
    state: ConnectionState = ConnectionState.CONNECTING
    metadata: dict[str, Any] = field(default_factory=dict)
    current_request_id: str | None = None

    @property
    def connection_duration(self) -> float:
        """Get connection duration in seconds."""
        return time.time() - self.connected_at

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "client_id": self.client_id,
            "state": self.state.value,
            "connected_at": self.connected_at,
            "duration_seconds": round(self.connection_duration, 2),
            "current_request_id": self.current_request_id,
            "metadata": self.metadata,
        }


class ConnectionManager:
    """
    Manages WebSocket connections for streaming.

    Provides:
    - Connection tracking and lifecycle management
    - Message broadcasting to single or multiple clients
    - Request-specific streaming sessions
    - Connection statistics and health monitoring
    """

    def __init__(
        self,
        max_connections: int = 100,
        heartbeat_interval: float = 30.0,
    ) -> None:
        """
        Initialize connection manager.

        Args:
            max_connections: Maximum concurrent connections allowed
            heartbeat_interval: Interval in seconds for heartbeat pings
        """
        self.max_connections = max_connections
        self.heartbeat_interval = heartbeat_interval
        self._clients: dict[str, StreamingClient] = {}
        self._request_clients: dict[str, set[str]] = {}  # request_id -> client_ids
        self._lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task | None = None
        self._running = False

        # Callbacks
        self._on_connect: Callable[[StreamingClient], Coroutine[Any, Any, None]] | None = None
        self._on_disconnect: Callable[[StreamingClient], Coroutine[Any, Any, None]] | None = None

    @property
    def connection_count(self) -> int:
        """Get current number of connections."""
        return len(self._clients)

    @property
    def is_at_capacity(self) -> bool:
        """Check if connection limit is reached."""
        return self.connection_count >= self.max_connections

    def set_on_connect(
        self, callback: Callable[[StreamingClient], Coroutine[Any, Any, None]]
    ) -> None:
        """Set callback for new connections."""
        self._on_connect = callback

    def set_on_disconnect(
        self, callback: Callable[[StreamingClient], Coroutine[Any, Any, None]]
    ) -> None:
        """Set callback for disconnections."""
        self._on_disconnect = callback

    async def start(self) -> None:
        """Start the connection manager (heartbeat task)."""
        if self._running:
            return
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("Connection manager started")

    async def stop(self) -> None:
        """Stop the connection manager and close all connections."""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Close all connections
        async with self._lock:
            for client in list(self._clients.values()):
                await self._close_client(client)
            self._clients.clear()
            self._request_clients.clear()

        logger.info("Connection manager stopped")

    async def connect(
        self,
        websocket: WebSocket,
        client_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StreamingClient | None:
        """
        Accept a new WebSocket connection.

        Args:
            websocket: The WebSocket connection
            client_id: Optional client identifier (generated if not provided)
            metadata: Optional metadata to attach to the client

        Returns:
            StreamingClient if connected, None if rejected
        """
        if self.is_at_capacity:
            logger.warning(f"Connection rejected: at capacity ({self.max_connections})")
            await websocket.close(code=1013, reason="Server at capacity")
            return None

        async with self._lock:
            client_id = client_id or str(uuid.uuid4())

            # Accept the connection
            await websocket.accept()

            client = StreamingClient(
                client_id=client_id,
                websocket=websocket,
                state=ConnectionState.CONNECTED,
                metadata=metadata or {},
            )
            self._clients[client_id] = client

            logger.info(f"Client connected: {client_id}")

            if self._on_connect:
                try:
                    await self._on_connect(client)
                except Exception as e:
                    logger.error(f"Error in on_connect callback: {e}")

            return client

    async def disconnect(self, client_id: str) -> None:
        """
        Disconnect a client.

        Args:
            client_id: The client identifier
        """
        async with self._lock:
            client = self._clients.pop(client_id, None)
            if client:
                await self._close_client(client)

                # Remove from request mappings
                for request_clients in self._request_clients.values():
                    request_clients.discard(client_id)

                logger.info(f"Client disconnected: {client_id}")

                if self._on_disconnect:
                    try:
                        await self._on_disconnect(client)
                    except Exception as e:
                        logger.error(f"Error in on_disconnect callback: {e}")

    async def _close_client(self, client: StreamingClient) -> None:
        """Close a client connection safely."""
        client.state = ConnectionState.CLOSING
        try:
            await client.websocket.close()
        except Exception:
            pass
        client.state = ConnectionState.CLOSED

    async def send_to_client(
        self,
        client_id: str,
        message: dict[str, Any],
    ) -> bool:
        """
        Send a message to a specific client.

        Args:
            client_id: Target client identifier
            message: Message to send (will be JSON encoded)

        Returns:
            True if sent successfully, False otherwise
        """
        client = self._clients.get(client_id)
        if not client or client.state not in (
            ConnectionState.CONNECTED,
            ConnectionState.STREAMING,
        ):
            return False

        try:
            await client.websocket.send_json(message)
            return True
        except Exception as e:
            logger.warning(f"Failed to send to client {client_id}: {e}")
            await self.disconnect(client_id)
            return False

    async def send_text_to_client(
        self,
        client_id: str,
        text: str,
    ) -> bool:
        """
        Send raw text to a specific client.

        Args:
            client_id: Target client identifier
            text: Text to send

        Returns:
            True if sent successfully, False otherwise
        """
        client = self._clients.get(client_id)
        if not client or client.state not in (
            ConnectionState.CONNECTED,
            ConnectionState.STREAMING,
        ):
            return False

        try:
            await client.websocket.send_text(text)
            return True
        except Exception as e:
            logger.warning(f"Failed to send text to client {client_id}: {e}")
            await self.disconnect(client_id)
            return False

    async def broadcast(
        self,
        message: dict[str, Any],
        exclude: set[str] | None = None,
    ) -> int:
        """
        Broadcast a message to all connected clients.

        Args:
            message: Message to broadcast
            exclude: Set of client IDs to exclude

        Returns:
            Number of clients that received the message
        """
        exclude = exclude or set()
        sent_count = 0

        for client_id in list(self._clients.keys()):
            if client_id not in exclude:
                if await self.send_to_client(client_id, message):
                    sent_count += 1

        return sent_count

    async def send_to_request(
        self,
        request_id: str,
        message: dict[str, Any],
    ) -> int:
        """
        Send a message to all clients subscribed to a request.

        Args:
            request_id: The request identifier
            message: Message to send

        Returns:
            Number of clients that received the message
        """
        client_ids = self._request_clients.get(request_id, set())
        sent_count = 0

        for client_id in list(client_ids):
            if await self.send_to_client(client_id, message):
                sent_count += 1

        return sent_count

    def subscribe_to_request(self, client_id: str, request_id: str) -> bool:
        """
        Subscribe a client to a specific request's stream.

        Args:
            client_id: The client identifier
            request_id: The request identifier

        Returns:
            True if subscription successful
        """
        client = self._clients.get(client_id)
        if not client:
            return False

        if request_id not in self._request_clients:
            self._request_clients[request_id] = set()

        self._request_clients[request_id].add(client_id)
        client.current_request_id = request_id
        client.state = ConnectionState.STREAMING

        return True

    def unsubscribe_from_request(self, client_id: str, request_id: str) -> bool:
        """
        Unsubscribe a client from a request's stream.

        Args:
            client_id: The client identifier
            request_id: The request identifier

        Returns:
            True if unsubscription successful
        """
        client = self._clients.get(client_id)
        if client:
            client.current_request_id = None
            client.state = ConnectionState.CONNECTED

        if request_id in self._request_clients:
            self._request_clients[request_id].discard(client_id)
            if not self._request_clients[request_id]:
                del self._request_clients[request_id]
            return True

        return False

    def get_client(self, client_id: str) -> StreamingClient | None:
        """Get a client by ID."""
        return self._clients.get(client_id)

    def get_all_clients(self) -> list[StreamingClient]:
        """Get all connected clients."""
        return list(self._clients.values())

    def get_stats(self) -> dict[str, Any]:
        """Get connection statistics."""
        states = {}
        for client in self._clients.values():
            state = client.state.value
            states[state] = states.get(state, 0) + 1

        return {
            "total_connections": self.connection_count,
            "max_connections": self.max_connections,
            "at_capacity": self.is_at_capacity,
            "active_requests": len(self._request_clients),
            "states": states,
        }

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to all clients."""
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)

                if not self._running:
                    break

                # Send ping to all clients
                disconnected = []
                for client_id, client in list(self._clients.items()):
                    try:
                        await client.websocket.send_json({"type": "ping"})
                    except Exception:
                        disconnected.append(client_id)

                # Clean up disconnected clients
                for client_id in disconnected:
                    await self.disconnect(client_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")


# Global default instance
default_connection_manager = ConnectionManager()
