"""Tests for security module: URL validation and API key middleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrator.security import (
    UrlValidator,
    UrlValidationError,
    ApiKeyMiddleware,
)


class TestUrlValidator:
    """Tests for UrlValidator."""

    @pytest.fixture
    def validator(self) -> UrlValidator:
        return UrlValidator()

    def test_valid_external_url(self, validator: UrlValidator) -> None:
        """Test valid external URL passes."""
        url = "https://openrouter.ai/api/v1/models"
        result = validator.validate(url)
        assert result == url

    def test_valid_http_url(self, validator: UrlValidator) -> None:
        """Test HTTP scheme is allowed."""
        url = "http://example.com/api"
        result = validator.validate(url)
        assert result == url

    def test_blocks_private_ip_10(self, validator: UrlValidator) -> None:
        """Test blocks 10.x.x.x range."""
        with pytest.raises(UrlValidationError, match="Private IP"):
            validator.validate("http://10.0.0.1/api")

    def test_blocks_private_ip_192(self, validator: UrlValidator) -> None:
        """Test blocks 192.168.x.x range."""
        with pytest.raises(UrlValidationError, match="Private IP"):
            validator.validate("http://192.168.1.1/api")

    def test_blocks_private_ip_172(self, validator: UrlValidator) -> None:
        """Test blocks 172.16.x.x range."""
        with pytest.raises(UrlValidationError, match="Private IP"):
            validator.validate("http://172.16.0.1/api")

    def test_blocks_localhost(self, validator: UrlValidator) -> None:
        """Test blocks localhost hostname."""
        with pytest.raises(UrlValidationError, match="Blocked hostname"):
            validator.validate("http://localhost/api")

    def test_blocks_loopback(self, validator: UrlValidator) -> None:
        """Test blocks 127.0.0.1."""
        with pytest.raises(UrlValidationError, match="Private IP"):
            validator.validate("http://127.0.0.1/api")

    def test_blocks_invalid_scheme(self, validator: UrlValidator) -> None:
        """Test blocks non-http schemes."""
        with pytest.raises(UrlValidationError, match="Invalid scheme"):
            validator.validate("file:///etc/passwd")

    def test_blocks_ftp_scheme(self, validator: UrlValidator) -> None:
        """Test blocks FTP scheme."""
        with pytest.raises(UrlValidationError, match="Invalid scheme"):
            validator.validate("ftp://example.com/file")

    def test_blocks_empty_url(self, validator: UrlValidator) -> None:
        """Test blocks empty URL."""
        with pytest.raises(UrlValidationError, match="Empty URL"):
            validator.validate("")

    def test_is_valid_helper(self, validator: UrlValidator) -> None:
        """Test is_valid helper method."""
        assert validator.is_valid("https://example.com")
        assert not validator.is_valid("http://localhost")
        assert not validator.is_valid("http://192.168.1.1")

    def test_allowlist_enforced(self) -> None:
        """Test domain allowlist is enforced."""
        validator = UrlValidator(allowed_domains=["openrouter.ai", "huggingface.co"])
        
        # Allowed
        assert validator.is_valid("https://openrouter.ai/api")
        assert validator.is_valid("https://api.huggingface.co/models")
        
        # Not allowed
        assert not validator.is_valid("https://example.com/api")

    def test_allowlist_subdomain_match(self) -> None:
        """Test subdomains match allowlist."""
        validator = UrlValidator(allowed_domains=["example.com"])
        
        assert validator.is_valid("https://api.example.com/v1")
        assert validator.is_valid("https://sub.sub.example.com/v1")


class TestApiKeyMiddleware:
    """Tests for ApiKeyMiddleware."""

    @pytest.fixture
    def app_with_auth(self) -> FastAPI:
        """Create app with API key auth."""
        app = FastAPI()
        app.add_middleware(ApiKeyMiddleware, api_key="test-secret-key")
        
        @app.get("/health")
        def health():
            return {"status": "ok"}
        
        @app.get("/protected")
        def protected():
            return {"data": "secret"}
        
        return app

    @pytest.fixture
    def client(self, app_with_auth: FastAPI) -> TestClient:
        return TestClient(app_with_auth)

    def test_health_bypasses_auth(self, client: TestClient) -> None:
        """Test health endpoint doesn't require auth."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_protected_requires_auth(self, client: TestClient) -> None:
        """Test protected endpoint requires auth."""
        response = client.get("/protected")
        assert response.status_code == 401

    def test_missing_header_returns_401(self, client: TestClient) -> None:
        """Test missing Authorization header returns 401."""
        response = client.get("/protected")
        assert response.status_code == 401
        assert "Missing Authorization" in response.json()["error"]

    def test_invalid_format_returns_401(self, client: TestClient) -> None:
        """Test invalid header format returns 401."""
        response = client.get("/protected", headers={"Authorization": "Basic abc123"})
        assert response.status_code == 401
        assert "Invalid Authorization" in response.json()["error"]

    def test_wrong_key_returns_401(self, client: TestClient) -> None:
        """Test wrong API key returns 401."""
        response = client.get("/protected", headers={"Authorization": "Bearer wrong-key"})
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["error"]

    def test_valid_key_succeeds(self, client: TestClient) -> None:
        """Test valid API key allows access."""
        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer test-secret-key"}
        )
        assert response.status_code == 200
        assert response.json()["data"] == "secret"
