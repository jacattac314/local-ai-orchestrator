"""Tests for budget management service."""

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.analytics.budget import (
    BudgetConfig,
    BudgetManager,
    BudgetPeriod,
    BudgetStatus,
    SpendSummary,
)


class TestBudgetConfig:
    """Tests for BudgetConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = BudgetConfig()
        assert config.daily_limit == 10.0
        assert config.weekly_limit == 50.0
        assert config.monthly_limit == 100.0
        assert config.alert_threshold == 0.8
        assert config.hard_limit is False

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = BudgetConfig(
            daily_limit=25.0,
            weekly_limit=100.0,
            monthly_limit=300.0,
            alert_threshold=0.9,
            hard_limit=True,
        )
        assert config.daily_limit == 25.0
        assert config.weekly_limit == 100.0
        assert config.monthly_limit == 300.0
        assert config.alert_threshold == 0.9
        assert config.hard_limit is True

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        config = BudgetConfig(daily_limit=15.0, hard_limit=True)
        data = config.to_dict()

        assert data["daily_limit"] == 15.0
        assert data["hard_limit"] is True
        assert "weekly_limit" in data
        assert "monthly_limit" in data
        assert "alert_threshold" in data

    def test_from_dict(self) -> None:
        """Test deserialization from dictionary."""
        data = {
            "daily_limit": 20.0,
            "weekly_limit": 80.0,
            "monthly_limit": 200.0,
            "alert_threshold": 0.75,
            "hard_limit": True,
        }
        config = BudgetConfig.from_dict(data)

        assert config.daily_limit == 20.0
        assert config.weekly_limit == 80.0
        assert config.monthly_limit == 200.0
        assert config.alert_threshold == 0.75
        assert config.hard_limit is True

    def test_from_dict_with_defaults(self) -> None:
        """Test from_dict uses defaults for missing keys."""
        config = BudgetConfig.from_dict({})

        assert config.daily_limit == 10.0
        assert config.weekly_limit == 50.0
        assert config.monthly_limit == 100.0


class TestSpendSummary:
    """Tests for SpendSummary dataclass."""

    def test_default_values(self) -> None:
        """Test default summary values."""
        summary = SpendSummary()
        assert summary.daily_spend == 0.0
        assert summary.weekly_spend == 0.0
        assert summary.monthly_spend == 0.0
        assert summary.status == BudgetStatus.OK

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        summary = SpendSummary(
            daily_spend=5.0,
            daily_remaining=5.0,
            daily_percent=50.0,
            status=BudgetStatus.WARNING,
            status_message="Approaching limit",
        )
        data = summary.to_dict()

        assert data["daily_spend"] == 5.0
        assert data["daily_remaining"] == 5.0
        assert data["daily_percent"] == 50.0
        assert data["status"] == "warning"
        assert data["status_message"] == "Approaching limit"


class TestBudgetPeriod:
    """Tests for BudgetPeriod enum."""

    def test_period_values(self) -> None:
        """Test period enum values."""
        assert BudgetPeriod.DAILY.value == "daily"
        assert BudgetPeriod.WEEKLY.value == "weekly"
        assert BudgetPeriod.MONTHLY.value == "monthly"


class TestBudgetStatus:
    """Tests for BudgetStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert BudgetStatus.OK.value == "ok"
        assert BudgetStatus.WARNING.value == "warning"
        assert BudgetStatus.EXCEEDED.value == "exceeded"


class TestBudgetManager:
    """Tests for BudgetManager."""

    @pytest.fixture
    def temp_config_path(self) -> str:
        """Create a temporary config file path."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        yield path
        try:
            os.unlink(path)
        except OSError:
            pass

    @pytest.fixture
    def mock_storage(self) -> MagicMock:
        """Create a mock analytics storage."""
        storage = MagicMock()
        storage.get_summary.return_value = {
            "estimated_cost": 0.0,
            "total_requests": 0,
        }
        return storage

    def test_initialize(self, mock_storage: MagicMock, temp_config_path: str) -> None:
        """Test manager initialization."""
        manager = BudgetManager()
        manager.initialize(mock_storage, temp_config_path)

        assert manager._initialized is True
        assert manager.storage == mock_storage
        assert manager.config_path == temp_config_path

    def test_initialize_loads_existing_config(
        self, mock_storage: MagicMock, temp_config_path: str
    ) -> None:
        """Test that initialize loads existing config file."""
        # Write a config file first
        config_data = {
            "daily_limit": 25.0,
            "weekly_limit": 75.0,
            "monthly_limit": 150.0,
            "alert_threshold": 0.7,
            "hard_limit": True,
        }
        with open(temp_config_path, "w") as f:
            json.dump(config_data, f)

        manager = BudgetManager()
        manager.initialize(mock_storage, temp_config_path)

        assert manager.config.daily_limit == 25.0
        assert manager.config.hard_limit is True

    def test_save_config(
        self, mock_storage: MagicMock, temp_config_path: str
    ) -> None:
        """Test saving configuration to file."""
        manager = BudgetManager()
        manager.initialize(mock_storage, temp_config_path)
        manager.config.daily_limit = 30.0
        manager.save_config()

        with open(temp_config_path) as f:
            saved = json.load(f)

        assert saved["daily_limit"] == 30.0

    def test_update_config(
        self, mock_storage: MagicMock, temp_config_path: str
    ) -> None:
        """Test updating configuration values."""
        manager = BudgetManager()
        manager.initialize(mock_storage, temp_config_path)

        updated = manager.update_config(
            daily_limit=20.0,
            hard_limit=True,
        )

        assert updated.daily_limit == 20.0
        assert updated.hard_limit is True
        # Other values unchanged
        assert updated.weekly_limit == 50.0

    def test_update_config_clamps_values(
        self, mock_storage: MagicMock, temp_config_path: str
    ) -> None:
        """Test that update_config clamps values to valid ranges."""
        manager = BudgetManager()
        manager.initialize(mock_storage, temp_config_path)

        # Negative limits should be clamped to 0
        manager.update_config(daily_limit=-10.0)
        assert manager.config.daily_limit == 0.0

        # Alert threshold should be clamped to 0-1
        manager.update_config(alert_threshold=1.5)
        assert manager.config.alert_threshold == 1.0

        manager.update_config(alert_threshold=-0.5)
        assert manager.config.alert_threshold == 0.0


class TestSpendSummaryCalculation:
    """Tests for spend summary calculation."""

    @pytest.fixture
    def manager_with_storage(self, temp_config_path: str) -> BudgetManager:
        """Create a manager with mocked storage."""
        manager = BudgetManager()
        storage = MagicMock()
        manager.initialize(storage, temp_config_path)
        return manager

    def test_get_spend_summary_no_storage(self) -> None:
        """Test summary when storage is not initialized."""
        manager = BudgetManager()
        summary = manager.get_spend_summary()

        assert summary.daily_spend == 0.0
        assert summary.status == BudgetStatus.OK

    def test_get_spend_summary_ok_status(
        self, manager_with_storage: BudgetManager
    ) -> None:
        """Test summary with healthy budget status."""
        manager_with_storage.storage.get_summary.return_value = {
            "estimated_cost": 2.0,  # Well under daily limit of 10
        }

        summary = manager_with_storage.get_spend_summary()

        assert summary.status == BudgetStatus.OK
        assert summary.daily_spend == 2.0
        assert summary.daily_remaining == 8.0
        assert summary.daily_percent == pytest.approx(20.0, rel=0.01)

    def test_get_spend_summary_warning_status(
        self, manager_with_storage: BudgetManager
    ) -> None:
        """Test summary with warning status (approaching limit)."""
        # 85% of daily limit (10.0) = 8.5
        manager_with_storage.storage.get_summary.return_value = {
            "estimated_cost": 8.5,
        }

        summary = manager_with_storage.get_spend_summary()

        assert summary.status == BudgetStatus.WARNING
        assert "daily" in summary.status_message.lower()

    def test_get_spend_summary_exceeded_status(
        self, manager_with_storage: BudgetManager
    ) -> None:
        """Test summary with exceeded status."""
        # Over daily limit
        manager_with_storage.storage.get_summary.return_value = {
            "estimated_cost": 15.0,
        }

        summary = manager_with_storage.get_spend_summary()

        assert summary.status == BudgetStatus.EXCEEDED
        assert "exceeded" in summary.status_message.lower()

    def test_get_spend_summary_disabled_limit(
        self, manager_with_storage: BudgetManager
    ) -> None:
        """Test that disabled limits (0) don't trigger warnings."""
        manager_with_storage.config.daily_limit = 0.0  # Disabled

        manager_with_storage.storage.get_summary.return_value = {
            "estimated_cost": 1000.0,  # Any amount
        }

        summary = manager_with_storage.get_spend_summary()

        # Should still show spend but not trigger daily warning
        assert summary.daily_percent == 0.0


class TestBudgetEnforcement:
    """Tests for budget enforcement logic."""

    @pytest.fixture
    def enforcing_manager(self, temp_config_path: str) -> BudgetManager:
        """Create a manager with hard limits enabled."""
        manager = BudgetManager()
        storage = MagicMock()
        storage.get_summary.return_value = {"estimated_cost": 0.0}
        manager.initialize(storage, temp_config_path)
        manager.config.hard_limit = True
        return manager

    def test_check_allowed_advisory_mode(self, temp_config_path: str) -> None:
        """Test that advisory mode always allows requests."""
        manager = BudgetManager()
        storage = MagicMock()
        storage.get_summary.return_value = {"estimated_cost": 1000.0}  # Over limit
        manager.initialize(storage, temp_config_path)
        manager.config.hard_limit = False  # Advisory only

        allowed, reason = manager.check_budget_allowed(estimated_cost=100.0)

        assert allowed is True
        assert "advisory" in reason.lower()

    def test_check_allowed_under_budget(
        self, enforcing_manager: BudgetManager
    ) -> None:
        """Test allowing requests under budget."""
        enforcing_manager.storage.get_summary.return_value = {
            "estimated_cost": 2.0,
        }

        allowed, reason = enforcing_manager.check_budget_allowed(estimated_cost=1.0)

        assert allowed is True
        assert "within budget" in reason.lower()

    def test_check_blocked_exceeded(
        self, enforcing_manager: BudgetManager
    ) -> None:
        """Test blocking when budget exceeded."""
        enforcing_manager.storage.get_summary.return_value = {
            "estimated_cost": 15.0,  # Over daily limit
        }

        allowed, reason = enforcing_manager.check_budget_allowed(estimated_cost=0.0)

        assert allowed is False
        assert "exceeded" in reason.lower()

    def test_check_blocked_would_exceed(
        self, enforcing_manager: BudgetManager
    ) -> None:
        """Test blocking when request would exceed budget."""
        enforcing_manager.storage.get_summary.return_value = {
            "estimated_cost": 8.0,  # Under limit
        }

        # This would push us over the 10.0 daily limit
        allowed, reason = enforcing_manager.check_budget_allowed(estimated_cost=5.0)

        assert allowed is False
        assert "would exceed" in reason.lower()

    def test_check_allowed_exact_limit(
        self, enforcing_manager: BudgetManager
    ) -> None:
        """Test edge case at exact limit."""
        enforcing_manager.storage.get_summary.return_value = {
            "estimated_cost": 9.0,
        }

        # This brings us exactly to the limit
        allowed, reason = enforcing_manager.check_budget_allowed(estimated_cost=1.0)

        assert allowed is True


class TestBudgetStatusAPI:
    """Tests for budget status API response."""

    def test_get_budget_status(self, temp_config_path: str) -> None:
        """Test complete budget status response."""
        manager = BudgetManager()
        storage = MagicMock()
        storage.get_summary.return_value = {"estimated_cost": 5.0}
        manager.initialize(storage, temp_config_path)

        status = manager.get_budget_status()

        assert "config" in status
        assert "spend" in status
        assert "enforcement" in status
        assert status["enforcement"] == "advisory"
        assert status["config"]["daily_limit"] == 10.0

    def test_get_budget_status_hard_limit(self, temp_config_path: str) -> None:
        """Test budget status with hard limit enabled."""
        manager = BudgetManager()
        storage = MagicMock()
        storage.get_summary.return_value = {"estimated_cost": 0.0}
        manager.initialize(storage, temp_config_path)
        manager.config.hard_limit = True

        status = manager.get_budget_status()

        assert status["enforcement"] == "hard"


class TestConfigPersistence:
    """Tests for configuration file persistence."""

    def test_config_persists_across_instances(self, temp_config_path: str) -> None:
        """Test that config changes persist across manager instances."""
        storage = MagicMock()
        storage.get_summary.return_value = {"estimated_cost": 0.0}

        # First instance - update config
        manager1 = BudgetManager()
        manager1.initialize(storage, temp_config_path)
        manager1.update_config(daily_limit=42.0, hard_limit=True)

        # Second instance - should load saved config
        manager2 = BudgetManager()
        manager2.initialize(storage, temp_config_path)

        assert manager2.config.daily_limit == 42.0
        assert manager2.config.hard_limit is True

    def test_handles_corrupted_config_file(self, temp_config_path: str) -> None:
        """Test graceful handling of corrupted config file."""
        # Write invalid JSON
        with open(temp_config_path, "w") as f:
            f.write("not valid json {{{")

        storage = MagicMock()
        storage.get_summary.return_value = {"estimated_cost": 0.0}

        manager = BudgetManager()
        manager.initialize(storage, temp_config_path)

        # Should fall back to defaults
        assert manager.config.daily_limit == 10.0

    def test_creates_config_directory(self) -> None:
        """Test that config file parent directories are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "nested", "dir", "config.json")

            storage = MagicMock()
            storage.get_summary.return_value = {"estimated_cost": 0.0}

            manager = BudgetManager()
            manager.initialize(storage, config_path)
            manager.update_config(daily_limit=99.0)

            assert Path(config_path).exists()


# Additional fixture for manager tests
@pytest.fixture
def temp_config_path() -> str:
    """Create a temporary config file path."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass
