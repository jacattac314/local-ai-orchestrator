"""
Server-Sent Events (SSE) handler for streaming responses.

Provides SSE streaming support as an alternative to WebSockets,
compatible with the OpenAI streaming format.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)


def format_sse_event(
    data: Any,
    event: str | None = None,
    id: str | None = None,
    retry: int | None = None,
) -> str:
    """
    Format a Server-Sent Event.

    Args:
        data: Event data (will be JSON encoded if not a string)
        event: Optional event type
        id: Optional event ID
        retry: Optional retry time in milliseconds

    Returns:
        Formatted SSE string
    """
    lines = []

    if id is not None:
        lines.append(f"id: {id}")

    if event is not None:
        lines.append(f"event: {event}")

    if retry is not None:
        lines.append(f"retry: {retry}")

    # Handle data
    if isinstance(data, str):
        data_str = data
    else:
        data_str = json.dumps(data)

    # Split multi-line data
    for line in data_str.split("\n"):
        lines.append(f"data: {line}")

    return "\n".join(lines) + "\n\n"


@dataclass
class SSEChunk:
    """A chunk in an SSE stream."""

    id: str = "chatcmpl-stream"
    object: str = "chat.completion.chunk"
    model: str = ""
    delta_content: str = ""
    delta_role: str | None = None
    index: int = 0
    finish_reason: str | None = None
    created: int = field(default_factory=lambda: int(time.time()))

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI-compatible chunk format."""
        delta = {}
        if self.delta_role:
            delta["role"] = self.delta_role
        if self.delta_content:
            delta["content"] = self.delta_content

        return {
            "id": self.id,
            "object": self.object,
            "created": self.created,
            "model": self.model,
            "choices": [
                {
                    "index": self.index,
                    "delta": delta,
                    "finish_reason": self.finish_reason,
                }
            ],
        }


class SSEHandler:
    """
    Handles Server-Sent Events streaming.

    Provides OpenAI-compatible SSE streaming format
    with support for custom events and metadata.
    """

    def __init__(
        self,
        include_routing_info: bool = True,
        heartbeat_interval: float = 15.0,
    ) -> None:
        """
        Initialize SSE handler.

        Args:
            include_routing_info: Include routing metadata in stream
            heartbeat_interval: Interval for keep-alive comments (0 to disable)
        """
        self.include_routing_info = include_routing_info
        self.heartbeat_interval = heartbeat_interval

    async def create_stream(
        self,
        content_generator: AsyncIterator[str],
        model: str,
        routing_info: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> AsyncIterator[str]:
        """
        Create an SSE stream from a content generator.

        Args:
            content_generator: Async iterator yielding content chunks
            model: Model name for response
            routing_info: Optional routing metadata
            request_id: Optional request ID

        Yields:
            Formatted SSE event strings
        """
        request_id = request_id or str(uuid.uuid4())
        chunk_id = f"chatcmpl-{request_id[:8]}"
        created = int(time.time())
        chunk_index = 0

        # Send routing info first if enabled
        if self.include_routing_info and routing_info:
            yield format_sse_event(
                {"routing_info": routing_info},
                event="routing",
            )

        # Send initial chunk with role
        initial_chunk = SSEChunk(
            id=chunk_id,
            model=model,
            delta_role="assistant",
            created=created,
        )
        yield format_sse_event(initial_chunk.to_openai_format())

        # Stream content chunks
        last_heartbeat = time.time()

        async for content in content_generator:
            chunk = SSEChunk(
                id=chunk_id,
                model=model,
                delta_content=content,
                index=chunk_index,
                created=created,
            )
            yield format_sse_event(chunk.to_openai_format())
            chunk_index += 1

            # Send heartbeat if needed
            if self.heartbeat_interval > 0:
                now = time.time()
                if now - last_heartbeat >= self.heartbeat_interval:
                    yield ": heartbeat\n\n"
                    last_heartbeat = now

        # Send final chunk
        final_chunk = SSEChunk(
            id=chunk_id,
            model=model,
            index=chunk_index,
            finish_reason="stop",
            created=created,
        )
        yield format_sse_event(final_chunk.to_openai_format())

        # Send done marker
        yield "data: [DONE]\n\n"

    async def stream_with_usage(
        self,
        content_generator: AsyncIterator[str],
        model: str,
        prompt_tokens: int = 0,
        routing_info: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """
        Create an SSE stream that includes usage statistics at the end.

        Args:
            content_generator: Async iterator yielding content chunks
            model: Model name for response
            prompt_tokens: Number of prompt tokens
            routing_info: Optional routing metadata

        Yields:
            Formatted SSE event strings
        """
        request_id = str(uuid.uuid4())
        chunk_id = f"chatcmpl-{request_id[:8]}"
        created = int(time.time())
        chunk_index = 0
        total_content = ""

        # Send routing info
        if self.include_routing_info and routing_info:
            yield format_sse_event(
                {"routing_info": routing_info},
                event="routing",
            )

        # Initial role chunk
        initial_chunk = SSEChunk(
            id=chunk_id,
            model=model,
            delta_role="assistant",
            created=created,
        )
        yield format_sse_event(initial_chunk.to_openai_format())

        # Stream content
        async for content in content_generator:
            total_content += content
            chunk = SSEChunk(
                id=chunk_id,
                model=model,
                delta_content=content,
                index=chunk_index,
                created=created,
            )
            yield format_sse_event(chunk.to_openai_format())
            chunk_index += 1

        # Final chunk with finish reason
        final_chunk = SSEChunk(
            id=chunk_id,
            model=model,
            finish_reason="stop",
            created=created,
        )
        yield format_sse_event(final_chunk.to_openai_format())

        # Send usage statistics
        completion_tokens = len(total_content.split())  # Rough token estimate
        usage_event = {
            "object": "chat.completion.usage",
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
        yield format_sse_event(usage_event, event="usage")

        # Done marker
        yield "data: [DONE]\n\n"


def create_sse_response(
    content_generator: AsyncIterator[str],
    model: str,
    routing_info: dict[str, Any] | None = None,
    include_usage: bool = False,
    prompt_tokens: int = 0,
) -> StreamingResponse:
    """
    Create a FastAPI StreamingResponse for SSE.

    Args:
        content_generator: Async iterator yielding content strings
        model: Model name
        routing_info: Optional routing metadata
        include_usage: Whether to include usage stats at end
        prompt_tokens: Prompt token count for usage calculation

    Returns:
        FastAPI StreamingResponse
    """
    handler = SSEHandler()

    if include_usage:
        stream = handler.stream_with_usage(
            content_generator,
            model,
            prompt_tokens,
            routing_info,
        )
    else:
        stream = handler.create_stream(
            content_generator,
            model,
            routing_info,
        )

    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


async def mock_content_generator(
    text: str,
    delay: float = 0.05,
    word_by_word: bool = True,
) -> AsyncIterator[str]:
    """
    Mock content generator for testing.

    Args:
        text: Text to stream
        delay: Delay between chunks in seconds
        word_by_word: If True, yield word by word; otherwise character by character

    Yields:
        Content chunks
    """
    if word_by_word:
        words = text.split()
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            await asyncio.sleep(delay)
    else:
        for char in text:
            yield char
            await asyncio.sleep(delay)
