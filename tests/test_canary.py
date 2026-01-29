"""Canary tests for deployment health checks.

Run with: pytest -m canary
These tests are fast and verify critical system paths.
"""

import pytest


@pytest.mark.canary
class TestCanaryImports:
    """Verify all critical modules can be imported."""

    def test_import_core_modules(self) -> None:
        """Test core module imports."""
        from orchestrator.config import settings
        from orchestrator.db import DatabaseManager
        from orchestrator.scheduler import SchedulerService

        assert settings is not None
        assert DatabaseManager is not None
        assert SchedulerService is not None

    def test_import_routing_modules(self) -> None:
        """Test routing module imports."""
        from orchestrator.routing import (
            CompositeScorer,
            Router,
            BUILTIN_PROFILES,
        )
        from orchestrator.routing.complexity import ComplexityClassifier

        assert CompositeScorer is not None
        assert Router is not None
        assert len(BUILTIN_PROFILES) >= 4
        assert ComplexityClassifier is not None

    def test_import_api_modules(self) -> None:
        """Test API module imports."""
        from orchestrator.api import create_app

        assert create_app is not None

    def test_import_security_modules(self) -> None:
        """Test security module imports."""
        from orchestrator.security import UrlValidator, ApiKeyMiddleware
        from orchestrator.resilience import OfflineCache, DataPruner

        assert UrlValidator is not None
        assert ApiKeyMiddleware is not None
        assert OfflineCache is not None
        assert DataPruner is not None


@pytest.mark.canary
class TestCanaryConfig:
    """Verify configuration loads correctly."""

    def test_settings_load(self) -> None:
        """Test settings instance exists."""
        from orchestrator.config import settings

        assert settings.database_url is not None
        assert settings.api_host is not None
        assert settings.api_port > 0

    def test_data_dir_accessible(self) -> None:
        """Test data directory is configured."""
        from orchestrator.config import settings

        data_dir = settings.data_dir
        assert data_dir is not None


@pytest.mark.canary
class TestCanaryRouting:
    """Verify routing components work."""

    def test_router_initialization(self) -> None:
        """Test router can be created."""
        from orchestrator.routing import Router

        router = Router()
        assert router is not None

    def test_scorer_initialization(self) -> None:
        """Test scorer can be created."""
        from orchestrator.routing import CompositeScorer

        scorer = CompositeScorer()
        assert scorer is not None

    def test_complexity_classifier_initialization(self) -> None:
        """Test classifier can be created."""
        from orchestrator.routing.complexity import ComplexityClassifier

        classifier = ComplexityClassifier()
        assert classifier is not None

    def test_profile_lookup(self) -> None:
        """Test builtin profiles are accessible."""
        from orchestrator.routing import BUILTIN_PROFILES

        assert "balanced" in BUILTIN_PROFILES
        assert "quality" in BUILTIN_PROFILES
        assert "speed" in BUILTIN_PROFILES
        assert "budget" in BUILTIN_PROFILES


@pytest.mark.canary
class TestCanaryAPI:
    """Verify API can start."""

    def test_app_creation(self) -> None:
        """Test FastAPI app can be created."""
        from orchestrator.api import create_app

        app = create_app()
        assert app is not None
        assert app.title == "Local AI Orchestrator"

    def test_health_endpoint(self) -> None:
        """Test health endpoint responds."""
        from fastapi.testclient import TestClient
        from orchestrator.api import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
