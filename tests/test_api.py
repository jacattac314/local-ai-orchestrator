"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient

from orchestrator.api.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    app = create_app()
    return TestClient(app)


class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_check(self, client: TestClient) -> None:
        """Test health check returns healthy."""
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestRootEndpoint:
    """Tests for root endpoint."""

    def test_root(self, client: TestClient) -> None:
        """Test root endpoint."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "Local AI Orchestrator" in data["name"]


class TestChatCompletions:
    """Tests for chat completions endpoint."""

    def test_auto_routing(self, client: TestClient) -> None:
        """Test automatic model routing."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["model"]  # Should have a selected model
        assert data["routing_info"]["profile"] == "balanced"

    def test_manual_model(self, client: TestClient) -> None:
        """Test manual model selection."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["routing_info"]["profile"] == "manual"

    def test_custom_profile(self, client: TestClient) -> None:
        """Test custom routing profile."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": "Hello"}],
                "routing_profile": "speed",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["routing_info"]["profile"] == "speed"


class TestModelRankings:
    """Tests for model rankings endpoint."""

    def test_get_rankings(self, client: TestClient) -> None:
        """Test getting model rankings."""
        response = client.get("/v1/models/rankings")
        
        assert response.status_code == 200
        data = response.json()
        assert data["profile"] == "balanced"
        assert len(data["rankings"]) > 0
        assert data["rankings"][0]["rank"] == 1

    def test_rankings_with_profile(self, client: TestClient) -> None:
        """Test rankings with specific profile."""
        response = client.get("/v1/models/rankings?profile=quality")
        
        assert response.status_code == 200
        data = response.json()
        assert data["profile"] == "quality"

    def test_rankings_with_limit(self, client: TestClient) -> None:
        """Test rankings with limit."""
        response = client.get("/v1/models/rankings?limit=3")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["rankings"]) <= 3


class TestRoutingProfiles:
    """Tests for routing profiles endpoint."""

    def test_get_profiles(self, client: TestClient) -> None:
        """Test getting routing profiles."""
        response = client.get("/v1/routing/profiles")
        
        assert response.status_code == 200
        data = response.json()
        
        names = [p["name"] for p in data]
        assert "balanced" in names
        assert "quality" in names
        assert "speed" in names
        assert "budget" in names


class TestModelsList:
    """Tests for models list endpoint."""

    def test_list_models(self, client: TestClient) -> None:
        """Test listing available models."""
        response = client.get("/v1/models")
        
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "list"
        assert len(data["data"]) > 0
