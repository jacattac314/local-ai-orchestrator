"""Tests for database models."""

import pytest

from orchestrator.db.models import BenchmarkSourceRecord, Metric, Model, ModelAlias, RoutingIndex
from orchestrator.db.manager import DatabaseManager


class TestModel:
    """Tests for the Model class."""

    def test_create_model(self, db_manager: DatabaseManager) -> None:
        """Test creating a model."""
        with db_manager.get_session() as session:
            model = Model(
                name="openai/gpt-4",
                provider="openai",
                context_length=8192,
                active=True,
            )
            session.add(model)
            session.flush()

            assert model.id is not None
            assert model.created_at is not None

    def test_model_unique_name(self, db_manager: DatabaseManager) -> None:
        """Test that model names must be unique."""
        with pytest.raises(Exception):  # SQLAlchemy integrity error
            with db_manager.get_session() as session:
                model1 = Model(name="test-model", provider="test")
                model2 = Model(name="test-model", provider="test")
                session.add(model1)
                session.add(model2)


class TestMetric:
    """Tests for the Metric class."""

    def test_create_metric(self, db_manager: DatabaseManager) -> None:
        """Test creating a metric linked to a model."""
        from datetime import datetime

        with db_manager.get_session() as session:
            model = Model(name="test-model", provider="test")
            session.add(model)
            session.flush()

            metric = Metric(
                model_id=model.id,
                source="openrouter",
                metric_type="cost_blended_per_million",
                value=30.5,
                timestamp=datetime.utcnow(),
            )
            session.add(metric)
            session.flush()

            assert metric.id is not None
            assert metric.model_id == model.id

    def test_metric_relationship(self, db_manager: DatabaseManager) -> None:
        """Test the model-metric relationship."""
        from datetime import datetime

        with db_manager.get_session() as session:
            model = Model(name="test-model-rel", provider="test")
            session.add(model)
            session.flush()

            metric = Metric(
                model_id=model.id,
                source="test",
                metric_type="test_metric",
                value=1.0,
                timestamp=datetime.utcnow(),
            )
            session.add(metric)
            session.flush()

            # Query via relationship
            assert len(model.metrics) == 1
            assert model.metrics[0].metric_type == "test_metric"


class TestBenchmarkSourceRecord:
    """Tests for BenchmarkSourceRecord."""

    def test_create_source(self, db_manager: DatabaseManager) -> None:
        """Test creating a benchmark source record."""
        with db_manager.get_session() as session:
            source = BenchmarkSourceRecord(
                name="openrouter",
                url="https://openrouter.ai/api/v1/models",
                status="active",
            )
            session.add(source)
            session.flush()

            assert source.id is not None
            assert source.sync_interval_minutes == 60  # Default


class TestModelAlias:
    """Tests for ModelAlias."""

    def test_create_alias(self, db_manager: DatabaseManager) -> None:
        """Test creating a model alias."""
        with db_manager.get_session() as session:
            model = Model(name="canonical-model", provider="test")
            session.add(model)
            session.flush()

            alias = ModelAlias(
                alias="alternate-name",
                canonical_id=model.id,
                confidence=0.95,
                reviewed=False,
            )
            session.add(alias)
            session.flush()

            assert alias.canonical_model.name == "canonical-model"


class TestRoutingIndex:
    """Tests for RoutingIndex."""

    def test_create_routing_index(self, db_manager: DatabaseManager) -> None:
        """Test creating a routing index entry."""
        with db_manager.get_session() as session:
            model = Model(name="routed-model", provider="test")
            session.add(model)
            session.flush()

            index = RoutingIndex(
                model_id=model.id,
                profile="code_expert",
                score=0.85,
                quality_score=0.9,
                latency_score=0.8,
                cost_score=0.75,
            )
            session.add(index)
            session.flush()

            assert index.id is not None
            assert index.model.name == "routed-model"
