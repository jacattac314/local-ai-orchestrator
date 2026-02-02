"""
Tests for the streaming module.

Tests WebSocket connection management, SSE formatting,
and streaming handlers.
"""

import asyncio
import json
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator.streaming.manager import (
    ConnectionManager,
    ConnectionState,
    StreamingClient,
)
from orchestrator.streaming.websocket import (
    WebSocketHandler,
    StreamChunk,
    StreamEvent,
    create_websocket_handler,
)
from orchestrator.streaming.sse import (
    SSEHandler,
    SSEChunk,
    format_sse_event,
    mock_content_generator,
)


# --- StreamingClient Tests ---


class TestStreamingClient:
    """Tests for StreamingClient dataclass."""

    def test_create_client(self):
        """Test creating a streaming client."""
        websocket = MagicMock()
        client = StreamingClient(
            client_id="test-123",
            websocket=websocket,
        )

        assert client.client_id == "test-123"
        assert client.state == ConnectionState.CONNECTING
        assert client.current_request_id is None
        assert isinstance(client.connected_at, float)

    def test_connection_duration(self):
        """Test connection duration calculation."""
        websocket = MagicMock()
        client = StreamingClient(
            client_id="test",
            websocket=websocket,
            connected_at=time.time() - 10,  # 10 seconds ago
        )

        duration = client.connection_duration
        assert duration >= 10
        assert duration < 11

    def test_to_dict(self):
        """Test client serialization."""
        websocket = MagicMock()
        client = StreamingClient(
            client_id="test-abc",
            websocket=websocket,
            state=ConnectionState.STREAMING,
            current_request_id="req-123",
            metadata={"user": "test"},
        )

        data = client.to_dict()

        assert data["client_id"] == "test-abc"
        assert data["state"] == "streaming"
        assert data["current_request_id"] == "req-123"
        assert data["metadata"]["user"] == "test"
        assert "duration_seconds" in data


# --- ConnectionManager Tests ---


class TestConnectionManager:
    """Tests for ConnectionManager."""

    @pytest.fixture
    def manager(self):
        """Create a connection manager for testing."""
        return ConnectionManager(max_connections=5, heartbeat_interval=60.0)

    @pytest.mark.asyncio
    async def test_connect_client(self, manager):
        """Test accepting a new connection."""
        websocket = AsyncMock()

        client = await manager.connect(websocket, client_id="client-1")

        assert client is not None
        assert client.client_id == "client-1"
        assert client.state == ConnectionState.CONNECTED
        assert manager.connection_count == 1
        websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_at_capacity(self, manager):
        """Test rejecting connections at capacity."""
        # Fill up connections
        for i in range(5):
            ws = AsyncMock()
            await manager.connect(ws, client_id=f"client-{i}")

        assert manager.is_at_capacity

        # Try to connect one more
        extra_ws = AsyncMock()
        client = await manager.connect(extra_ws)

        assert client is None
        extra_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_client(self, manager):
        """Test disconnecting a client."""
        websocket = AsyncMock()
        client = await manager.connect(websocket, client_id="client-1")

        await manager.disconnect("client-1")

        assert manager.connection_count == 0
        assert manager.get_client("client-1") is None

    @pytest.mark.asyncio
    async def test_send_to_client(self, manager):
        """Test sending a message to a specific client."""
        websocket = AsyncMock()
        await manager.connect(websocket, client_id="client-1")

        message = {"type": "test", "data": "hello"}
        result = await manager.send_to_client("client-1", message)

        assert result is True
        websocket.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_client(self, manager):
        """Test sending to a client that doesn't exist."""
        result = await manager.send_to_client("nonexistent", {"test": True})
        assert result is False

    @pytest.mark.asyncio
    async def test_broadcast(self, manager):
        """Test broadcasting to all clients."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws3 = AsyncMock()

        await manager.connect(ws1, client_id="c1")
        await manager.connect(ws2, client_id="c2")
        await manager.connect(ws3, client_id="c3")

        message = {"type": "broadcast", "data": "hello all"}
        count = await manager.broadcast(message)

        assert count == 3
        ws1.send_json.assert_called_with(message)
        ws2.send_json.assert_called_with(message)
        ws3.send_json.assert_called_with(message)

    @pytest.mark.asyncio
    async def test_broadcast_with_exclude(self, manager):
        """Test broadcasting with exclusions."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await manager.connect(ws1, client_id="c1")
        await manager.connect(ws2, client_id="c2")

        message = {"type": "broadcast"}
        count = await manager.broadcast(message, exclude={"c1"})

        assert count == 1
        ws1.send_json.assert_not_called()
        ws2.send_json.assert_called_with(message)

    @pytest.mark.asyncio
    async def test_subscribe_to_request(self, manager):
        """Test subscribing a client to a request stream."""
        websocket = AsyncMock()
        await manager.connect(websocket, client_id="c1")

        result = manager.subscribe_to_request("c1", "req-123")

        assert result is True
        client = manager.get_client("c1")
        assert client.current_request_id == "req-123"
        assert client.state == ConnectionState.STREAMING

    @pytest.mark.asyncio
    async def test_send_to_request(self, manager):
        """Test sending to all clients subscribed to a request."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws3 = AsyncMock()

        await manager.connect(ws1, client_id="c1")
        await manager.connect(ws2, client_id="c2")
        await manager.connect(ws3, client_id="c3")

        # Subscribe c1 and c2 to the request
        manager.subscribe_to_request("c1", "req-123")
        manager.subscribe_to_request("c2", "req-123")

        message = {"type": "chunk", "content": "hello"}
        count = await manager.send_to_request("req-123", message)

        assert count == 2
        ws1.send_json.assert_called_with(message)
        ws2.send_json.assert_called_with(message)
        ws3.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_unsubscribe_from_request(self, manager):
        """Test unsubscribing from a request."""
        websocket = AsyncMock()
        await manager.connect(websocket, client_id="c1")
        manager.subscribe_to_request("c1", "req-123")

        result = manager.unsubscribe_from_request("c1", "req-123")

        assert result is True
        client = manager.get_client("c1")
        assert client.current_request_id is None
        assert client.state == ConnectionState.CONNECTED

    @pytest.mark.asyncio
    async def test_get_stats(self, manager):
        """Test getting connection statistics."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await manager.connect(ws1, client_id="c1")
        await manager.connect(ws2, client_id="c2")
        manager.subscribe_to_request("c1", "req-1")

        stats = manager.get_stats()

        assert stats["total_connections"] == 2
        assert stats["max_connections"] == 5
        assert stats["at_capacity"] is False
        assert stats["active_requests"] == 1
        assert "streaming" in stats["states"]
        assert "connected" in stats["states"]

    @pytest.mark.asyncio
    async def test_callbacks(self, manager):
        """Test on_connect and on_disconnect callbacks."""
        connected_clients = []
        disconnected_clients = []

        async def on_connect(client):
            connected_clients.append(client.client_id)

        async def on_disconnect(client):
            disconnected_clients.append(client.client_id)

        manager.set_on_connect(on_connect)
        manager.set_on_disconnect(on_disconnect)

        websocket = AsyncMock()
        await manager.connect(websocket, client_id="c1")
        await manager.disconnect("c1")

        assert "c1" in connected_clients
        assert "c1" in disconnected_clients


# --- StreamChunk and StreamEvent Tests ---


class TestStreamingDataClasses:
    """Tests for streaming data classes."""

    def test_stream_chunk_to_dict(self):
        """Test StreamChunk serialization."""
        chunk = StreamChunk(
            request_id="req-123",
            content="Hello",
            model="gpt-4",
            index=5,
            finish_reason=None,
            metadata={"tokens": 10},
        )

        data = chunk.to_dict()

        assert data["type"] == "chunk"
        assert data["request_id"] == "req-123"
        assert data["data"]["content"] == "Hello"
        assert data["data"]["model"] == "gpt-4"
        assert data["data"]["index"] == 5
        assert data["metadata"]["tokens"] == 10

    def test_stream_event_to_dict(self):
        """Test StreamEvent serialization."""
        event = StreamEvent(
            type="done",
            request_id="req-123",
            data={"total_chunks": 100},
        )

        data = event.to_dict()

        assert data["type"] == "done"
        assert data["request_id"] == "req-123"
        assert data["data"]["total_chunks"] == 100
        assert "timestamp" in data


# --- SSE Tests ---


class TestSSEFormatting:
    """Tests for SSE formatting functions."""

    def test_format_sse_event_basic(self):
        """Test basic SSE event formatting."""
        result = format_sse_event({"message": "hello"})

        assert "data: " in result
        assert result.endswith("\n\n")
        assert '"message": "hello"' in result

    def test_format_sse_event_with_type(self):
        """Test SSE event with event type."""
        result = format_sse_event({"test": True}, event="custom")

        assert "event: custom\n" in result
        assert "data: " in result

    def test_format_sse_event_with_id(self):
        """Test SSE event with ID."""
        result = format_sse_event("test", id="123")

        assert "id: 123\n" in result

    def test_format_sse_event_with_retry(self):
        """Test SSE event with retry interval."""
        result = format_sse_event("test", retry=5000)

        assert "retry: 5000\n" in result

    def test_format_sse_event_string_data(self):
        """Test SSE with string data (not JSON encoded)."""
        result = format_sse_event("[DONE]")

        assert "data: [DONE]\n" in result

    def test_format_sse_event_multiline(self):
        """Test SSE with multiline data."""
        result = format_sse_event("line1\nline2\nline3")

        assert "data: line1\n" in result
        assert "data: line2\n" in result
        assert "data: line3\n" in result


class TestSSEChunk:
    """Tests for SSEChunk dataclass."""

    def test_to_openai_format_with_content(self):
        """Test OpenAI format with content."""
        chunk = SSEChunk(
            id="chat-123",
            model="gpt-4",
            delta_content="Hello",
            index=0,
        )

        data = chunk.to_openai_format()

        assert data["id"] == "chat-123"
        assert data["object"] == "chat.completion.chunk"
        assert data["model"] == "gpt-4"
        assert data["choices"][0]["delta"]["content"] == "Hello"
        assert data["choices"][0]["finish_reason"] is None

    def test_to_openai_format_with_role(self):
        """Test OpenAI format with role."""
        chunk = SSEChunk(
            model="gpt-4",
            delta_role="assistant",
        )

        data = chunk.to_openai_format()

        assert data["choices"][0]["delta"]["role"] == "assistant"
        assert "content" not in data["choices"][0]["delta"]

    def test_to_openai_format_final_chunk(self):
        """Test OpenAI format for final chunk."""
        chunk = SSEChunk(
            model="gpt-4",
            finish_reason="stop",
        )

        data = chunk.to_openai_format()

        assert data["choices"][0]["finish_reason"] == "stop"
        assert data["choices"][0]["delta"] == {}


class TestSSEHandler:
    """Tests for SSEHandler."""

    @pytest.mark.asyncio
    async def test_create_stream_basic(self):
        """Test basic stream creation."""
        handler = SSEHandler(include_routing_info=False)

        async def content_gen():
            yield "Hello"
            yield " World"

        chunks = []
        async for chunk in handler.create_stream(content_gen(), "gpt-4"):
            chunks.append(chunk)

        # Should have: initial role, 2 content chunks, final chunk, [DONE]
        assert len(chunks) == 5

        # Check initial has role
        assert '"role": "assistant"' in chunks[0]

        # Check content chunks
        assert "Hello" in chunks[1]
        assert "World" in chunks[2]

        # Check final chunk
        assert '"finish_reason": "stop"' in chunks[3]

        # Check done marker
        assert "[DONE]" in chunks[4]

    @pytest.mark.asyncio
    async def test_create_stream_with_routing(self):
        """Test stream with routing info."""
        handler = SSEHandler(include_routing_info=True)

        async def content_gen():
            yield "test"

        routing_info = {"profile": "quality", "model": "gpt-4"}

        chunks = []
        async for chunk in handler.create_stream(
            content_gen(),
            "gpt-4",
            routing_info=routing_info,
        ):
            chunks.append(chunk)

        # First chunk should be routing event
        assert "event: routing" in chunks[0]
        assert "quality" in chunks[0]

    @pytest.mark.asyncio
    async def test_stream_with_usage(self):
        """Test stream with usage statistics."""
        handler = SSEHandler()

        async def content_gen():
            yield "one"
            yield " two"
            yield " three"

        chunks = []
        async for chunk in handler.stream_with_usage(
            content_gen(),
            "gpt-4",
            prompt_tokens=10,
        ):
            chunks.append(chunk)

        # Should include usage event
        usage_chunks = [c for c in chunks if "event: usage" in c]
        assert len(usage_chunks) == 1

        usage_chunk = usage_chunks[0]
        assert '"prompt_tokens": 10' in usage_chunk


class TestMockContentGenerator:
    """Tests for mock content generator."""

    @pytest.mark.asyncio
    async def test_word_by_word(self):
        """Test word-by-word generation."""
        chunks = []
        async for chunk in mock_content_generator("Hello World Test", delay=0.01):
            chunks.append(chunk)

        assert len(chunks) == 3
        assert chunks[0] == "Hello "
        assert chunks[1] == "World "
        assert chunks[2] == "Test"

    @pytest.mark.asyncio
    async def test_character_by_character(self):
        """Test character-by-character generation."""
        chunks = []
        async for chunk in mock_content_generator("Hi", delay=0.01, word_by_word=False):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0] == "H"
        assert chunks[1] == "i"


# --- WebSocket Handler Tests ---


class TestWebSocketHandler:
    """Tests for WebSocketHandler."""

    @pytest.fixture
    def manager(self):
        """Create a connection manager."""
        return ConnectionManager()

    @pytest.fixture
    def handler(self, manager):
        """Create a WebSocket handler with mock chat handler."""

        async def mock_chat_handler(request):
            for word in ["Hello", " ", "World"]:
                yield StreamChunk(
                    request_id="",
                    content=word,
                    model=request.get("model", "test"),
                )
                await asyncio.sleep(0.01)

        return create_websocket_handler(
            chat_handler=mock_chat_handler,
            connection_manager=manager,
        )

    def test_create_handler(self, handler, manager):
        """Test handler creation."""
        assert handler.manager is manager
        assert handler._chat_handler is not None

    @pytest.mark.asyncio
    async def test_handle_ping(self, handler, manager):
        """Test ping message handling."""
        from fastapi import WebSocketDisconnect

        websocket = AsyncMock()
        websocket.receive_json = AsyncMock(
            side_effect=[
                {"type": "ping"},
                WebSocketDisconnect(),  # Use WebSocketDisconnect to break the loop
            ]
        )

        client = await manager.connect(websocket, client_id="test")

        # Run message handling (will disconnect after ping)
        try:
            await handler._message_loop(client)
        except WebSocketDisconnect:
            pass

        # Check pong was sent
        calls = websocket.send_json.call_args_list
        pong_calls = [c for c in calls if c[0][0].get("type") == "pong"]
        assert len(pong_calls) >= 1


# --- Integration Tests ---


class TestStreamingIntegration:
    """Integration tests for streaming components."""

    @pytest.mark.asyncio
    async def test_full_streaming_flow(self):
        """Test complete streaming flow through manager."""
        manager = ConnectionManager()

        # Connect client
        ws = AsyncMock()
        client = await manager.connect(ws, client_id="c1")
        assert client is not None

        # Subscribe to request
        manager.subscribe_to_request("c1", "req-1")

        # Send stream chunks
        for i in range(3):
            await manager.send_to_request(
                "req-1",
                {"type": "chunk", "index": i, "content": f"chunk-{i}"},
            )

        # Verify all chunks received
        assert ws.send_json.call_count >= 3

        # Unsubscribe and disconnect
        manager.unsubscribe_from_request("c1", "req-1")
        await manager.disconnect("c1")

        assert manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_concurrent_streams(self):
        """Test multiple concurrent streaming clients."""
        manager = ConnectionManager()

        # Connect multiple clients
        clients = []
        for i in range(5):
            ws = AsyncMock()
            client = await manager.connect(ws, client_id=f"c{i}")
            clients.append((client, ws))

        # Subscribe to different requests
        manager.subscribe_to_request("c0", "req-a")
        manager.subscribe_to_request("c1", "req-a")
        manager.subscribe_to_request("c2", "req-b")

        # Send to request A
        await manager.send_to_request("req-a", {"type": "chunk", "data": "a"})

        # Verify correct clients received
        clients[0][1].send_json.assert_called()
        clients[1][1].send_json.assert_called()
        clients[2][1].send_json.assert_not_called()

        # Cleanup
        await manager.stop()
