"""Pytest configuration and fixtures."""

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from orchestrator.db.manager import DatabaseManager


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def db_manager(temp_db_path: str) -> Generator[DatabaseManager, None, None]:
    """Create a DatabaseManager with a temporary database."""
    manager = DatabaseManager(database_url=f"sqlite:///{temp_db_path}")
    manager.init_db()
    yield manager
    manager.close()


@pytest.fixture
def sample_openrouter_response() -> dict:
    """Sample OpenRouter API response for testing."""
    return {
        "data": [
            {
                "id": "openai/gpt-4",
                "name": "GPT-4",
                "description": "OpenAI's most capable model",
                "context_length": 8192,
                "pricing": {
                    "prompt": "0.00003",
                    "completion": "0.00006",
                    "request": "0",
                    "image": "0",
                },
                "top_provider": {
                    "latency_last_30m": {"p50": 500, "p90": 1200, "p95": 1800},
                    "ttft_last_30m": {"p90": 200},
                },
            },
            {
                "id": "anthropic/claude-3-opus",
                "name": "Claude 3 Opus",
                "description": "Anthropic's most capable model",
                "context_length": 200000,
                "pricing": {
                    "prompt": "0.000015",
                    "completion": "0.000075",
                    "request": "0",
                    "image": "0",
                },
                "top_provider": {
                    "latency_last_30m": {"p50": 400, "p90": 900},
                },
            },
        ]
    }
