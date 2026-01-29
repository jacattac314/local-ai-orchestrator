"""
Orchestrator API Client
HTTP client with sync and async support.
"""

from __future__ import annotations

import os
from typing import Generator, Optional

import httpx

from .models import (
    AnalyticsSummary,
    ChatCompletion,
    ChatMessage,
    ModelRanking,
    RoutingProfile,
    RoutingResult,
)


class OrchestratorClient:
    """
    Python client for the AI Orchestrator API.
    
    Example:
        ```python
        client = OrchestratorClient()
        
        # Get model rankings
        rankings = client.get_rankings(profile="quality", limit=5)
        
        # Chat completion with auto-routing
        response = client.chat("What is the capital of France?")
        print(response.content)
        
        # OpenAI-compatible interface
        response = client.chat_completions_create(
            messages=[{"role": "user", "content": "Hello!"}],
            model="auto",  # Let orchestrator decide
        )
        ```
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        timeout: float = 60.0,
    ):
        """
        Initialize the Orchestrator client.
        
        Args:
            base_url: API server URL (default: localhost:8000)
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("ORCHESTRATOR_API_KEY")
        self.timeout = timeout
        
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
        )
    
    def __enter__(self) -> OrchestratorClient:
        return self
    
    def __exit__(self, *args) -> None:
        self.close()
    
    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()
    
    # =========================================================================
    # Health & Info
    # =========================================================================
    
    def health(self) -> dict:
        """Check API health status."""
        response = self._client.get("/health")
        response.raise_for_status()
        return response.json()
    
    def is_healthy(self) -> bool:
        """Quick health check returning boolean."""
        try:
            health = self.health()
            return health.get("status") == "healthy"
        except Exception:
            return False
    
    # =========================================================================
    # Model Rankings
    # =========================================================================
    
    def get_rankings(
        self,
        profile: str = "balanced",
        limit: int = 10,
    ) -> list[ModelRanking]:
        """
        Get ranked models based on a routing profile.
        
        Args:
            profile: Routing profile (balanced, quality, speed, budget)
            limit: Maximum number of models to return
            
        Returns:
            List of ModelRanking objects sorted by score
        """
        response = self._client.get(
            "/v1/models/rankings",
            params={"profile": profile, "limit": limit},
        )
        response.raise_for_status()
        data = response.json()
        return [ModelRanking.from_dict(r) for r in data.get("rankings", [])]
    
    def get_best_model(self, profile: str = "balanced") -> Optional[ModelRanking]:
        """Get the top-ranked model for a profile."""
        rankings = self.get_rankings(profile=profile, limit=1)
        return rankings[0] if rankings else None
    
    # =========================================================================
    # Routing Profiles
    # =========================================================================
    
    def get_profiles(self) -> list[RoutingProfile]:
        """Get all available routing profiles."""
        response = self._client.get("/v1/routing_profiles")
        response.raise_for_status()
        data = response.json()
        return [
            RoutingProfile.from_dict(name, config)
            for name, config in data.get("profiles", {}).items()
        ]
    
    def get_profile(self, name: str) -> Optional[RoutingProfile]:
        """Get a specific routing profile by name."""
        profiles = self.get_profiles()
        for p in profiles:
            if p.name == name:
                return p
        return None
    
    # =========================================================================
    # Chat Completions (OpenAI-compatible)
    # =========================================================================
    
    def chat(
        self,
        message: str,
        model: str = "auto",
        profile: str = "balanced",
    ) -> ChatCompletion:
        """
        Simple chat interface - send a message, get a response.
        
        Args:
            message: The user message
            model: Model to use ("auto" for orchestrator routing)
            profile: Routing profile when model is "auto"
            
        Returns:
            ChatCompletion with the response
        """
        return self.chat_completions_create(
            messages=[{"role": "user", "content": message}],
            model=model,
            profile=profile,
        )
    
    def chat_completions_create(
        self,
        messages: list[dict],
        model: str = "auto",
        profile: str = "balanced",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> ChatCompletion | Generator[str, None, None]:
        """
        OpenAI-compatible chat completions endpoint.
        
        Args:
            messages: List of message dicts with role and content
            model: Model ID or "auto" for orchestrator routing
            profile: Routing profile (used when model="auto")
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            
        Returns:
            ChatCompletion or generator for streaming
        """
        payload = {
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "stream": stream,
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        if model == "auto":
            payload["routing_profile"] = profile
        
        if stream:
            return self._stream_chat(payload)
        
        response = self._client.post("/v1/chat/completions", json=payload)
        response.raise_for_status()
        return ChatCompletion.from_dict(response.json())
    
    def _stream_chat(self, payload: dict) -> Generator[str, None, None]:
        """Stream chat completion responses."""
        with self._client.stream("POST", "/v1/chat/completions", json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    yield data
    
    # =========================================================================
    # Analytics
    # =========================================================================
    
    def get_analytics_summary(
        self,
        period: str = "24h",
    ) -> AnalyticsSummary:
        """
        Get analytics summary for the specified period.
        
        Args:
            period: Time period (1h, 24h, 7d, 30d)
            
        Returns:
            AnalyticsSummary with usage stats
        """
        response = self._client.get(
            "/v1/analytics/summary",
            params={"period": period},
        )
        response.raise_for_status()
        return AnalyticsSummary.from_dict(response.json())
    
    # =========================================================================
    # Models List
    # =========================================================================
    
    def list_models(self) -> list[dict]:
        """Get list of all available models."""
        response = self._client.get("/v1/models")
        response.raise_for_status()
        return response.json().get("models", [])


class AsyncOrchestratorClient:
    """Async version of OrchestratorClient."""
    
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("ORCHESTRATOR_API_KEY")
        
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
        )
    
    async def __aenter__(self) -> AsyncOrchestratorClient:
        return self
    
    async def __aexit__(self, *args) -> None:
        await self.close()
    
    async def close(self) -> None:
        await self._client.aclose()
    
    async def health(self) -> dict:
        response = await self._client.get("/health")
        response.raise_for_status()
        return response.json()
    
    async def get_rankings(
        self,
        profile: str = "balanced",
        limit: int = 10,
    ) -> list[ModelRanking]:
        response = await self._client.get(
            "/v1/models/rankings",
            params={"profile": profile, "limit": limit},
        )
        response.raise_for_status()
        data = response.json()
        return [ModelRanking.from_dict(r) for r in data.get("rankings", [])]
    
    async def chat(
        self,
        message: str,
        model: str = "auto",
        profile: str = "balanced",
    ) -> ChatCompletion:
        payload = {
            "messages": [{"role": "user", "content": message}],
            "model": model,
            "temperature": 0.7,
            "stream": False,
        }
        if model == "auto":
            payload["routing_profile"] = profile
        
        response = await self._client.post("/v1/chat/completions", json=payload)
        response.raise_for_status()
        return ChatCompletion.from_dict(response.json())
