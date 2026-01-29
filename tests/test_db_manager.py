"""Tests for the DatabaseManager."""

import pytest

from orchestrator.db.manager import DatabaseManager


class TestDatabaseManager:
    """Tests for DatabaseManager."""

    def test_init_db(self, temp_db_path: str) -> None:
        """Test database initialization."""
        manager = DatabaseManager(database_url=f"sqlite:///{temp_db_path}")
        manager.init_db()

        # Tables should exist
        assert manager.health_check()
        manager.close()

    def test_health_check(self, db_manager: DatabaseManager) -> None:
        """Test health check."""
        assert db_manager.health_check() is True

    def test_session_context_manager(self, db_manager: DatabaseManager) -> None:
        """Test session context manager."""
        from orchestrator.db.models import Model

        with db_manager.get_session() as session:
            model = Model(name="test-session", provider="test")
            session.add(model)

        # Should be committed
        with db_manager.get_session() as session:
            result = session.query(Model).filter_by(name="test-session").first()
            assert result is not None

    def test_session_rollback_on_exception(self, db_manager: DatabaseManager) -> None:
        """Test that sessions rollback on exception."""
        from orchestrator.db.models import Model

        try:
            with db_manager.get_session() as session:
                model = Model(name="test-rollback", provider="test")
                session.add(model)
                raise ValueError("Simulated error")
        except ValueError:
            pass

        # Should NOT be committed
        with db_manager.get_session() as session:
            result = session.query(Model).filter_by(name="test-rollback").first()
            assert result is None

    def test_vacuum(self, db_manager: DatabaseManager) -> None:
        """Test vacuum operation."""
        # Should not raise
        db_manager.vacuum()
