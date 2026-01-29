"""Tests for resilience module: offline cache and data pruning."""

import json
import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.resilience import (
    CachedResponse,
    OfflineCache,
    DataPruner,
)


class TestCachedResponse:
    """Tests for CachedResponse dataclass."""

    def test_cached_at_property(self) -> None:
        """Test cached_at converts timestamp to datetime."""
        now = datetime.utcnow()
        cached = CachedResponse(
            source="test",
            data={"key": "value"},
            timestamp=now.isoformat(),
        )
        
        assert isinstance(cached.cached_at, datetime)
        assert cached.cached_at.date() == now.date()

    def test_age_seconds(self) -> None:
        """Test age_seconds calculates correctly."""
        old_time = datetime.utcnow() - timedelta(hours=2)
        cached = CachedResponse(
            source="test",
            data={},
            timestamp=old_time.isoformat(),
        )
        
        # Should be around 2 hours = 7200 seconds
        assert 7100 < cached.age_seconds < 7300

    def test_is_stale_within_max_age(self) -> None:
        """Test is_stale returns False for fresh cache."""
        now = datetime.utcnow()
        cached = CachedResponse(source="test", data={}, timestamp=now.isoformat())
        
        assert not cached.is_stale(max_age_hours=1)

    def test_is_stale_beyond_max_age(self) -> None:
        """Test is_stale returns True for old cache."""
        old_time = datetime.utcnow() - timedelta(hours=25)
        cached = CachedResponse(source="test", data={}, timestamp=old_time.isoformat())
        
        assert cached.is_stale(max_age_hours=24)


class TestOfflineCache:
    """Tests for OfflineCache."""

    @pytest.fixture
    def temp_cache_dir(self) -> Path:
        """Create temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def cache(self, temp_cache_dir: Path) -> OfflineCache:
        return OfflineCache(cache_dir=temp_cache_dir)

    def test_store_and_retrieve(self, cache: OfflineCache) -> None:
        """Test storing and retrieving data."""
        test_data = {"models": [{"id": 1}, {"id": 2}]}
        
        cache.store("openrouter", test_data)
        result = cache.retrieve("openrouter")
        
        assert result is not None
        assert result.source == "openrouter"
        assert result.data == test_data

    def test_retrieve_nonexistent(self, cache: OfflineCache) -> None:
        """Test retrieving non-existent key returns None."""
        result = cache.retrieve("nonexistent")
        assert result is None

    def test_memory_cache(self, cache: OfflineCache) -> None:
        """Test memory cache is used."""
        cache.store("test", {"key": "value"})
        
        # Should be in memory cache
        assert "test" in cache._memory_cache
        
        result = cache.retrieve("test")
        assert result is not None

    def test_disk_persistence(self, temp_cache_dir: Path) -> None:
        """Test data persists to disk."""
        cache1 = OfflineCache(cache_dir=temp_cache_dir)
        cache1.store("persistent", {"data": 123})
        
        # New cache instance should find the file
        cache2 = OfflineCache(cache_dir=temp_cache_dir)
        result = cache2.retrieve("persistent")
        
        assert result is not None
        assert result.data == {"data": 123}

    def test_retrieve_stale_returns_old_data(self, cache: OfflineCache) -> None:
        """Test retrieve_stale returns old data when needed."""
        # Store with old timestamp
        old_time = datetime.utcnow() - timedelta(hours=48)
        cache._memory_cache["test"] = CachedResponse(
            source="test",
            data={"old": "data"},
            timestamp=old_time.isoformat(),
        )
        
        # Normal retrieve should return None (too old)
        assert cache.retrieve("test", max_age_hours=1) is None
        
        # retrieve_stale should return the old data
        result = cache.retrieve_stale("test")
        assert result is not None
        assert result.data == {"old": "data"}

    def test_clear_specific_source(self, cache: OfflineCache) -> None:
        """Test clearing specific source."""
        cache.store("source1", {"data": 1})
        cache.store("source2", {"data": 2})
        
        cache.clear("source1")
        
        assert cache.retrieve("source1") is None
        assert cache.retrieve("source2") is not None

    def test_clear_all(self, cache: OfflineCache) -> None:
        """Test clearing all cache."""
        cache.store("source1", {"data": 1})
        cache.store("source2", {"data": 2})
        
        cache.clear()
        
        assert cache.retrieve("source1") is None
        assert cache.retrieve("source2") is None


class TestDataPruner:
    """Tests for DataPruner."""

    def test_prune_without_db_manager(self) -> None:
        """Test pruning without db_manager returns 0."""
        pruner = DataPruner(retention_days=30)
        
        result = pruner.prune_metrics()
        assert result == 0

    def test_set_db_manager(self) -> None:
        """Test setting db_manager."""
        pruner = DataPruner()
        mock_db = MagicMock()
        
        pruner.set_db_manager(mock_db)
        
        assert pruner._db_manager == mock_db

    def test_run_all(self) -> None:
        """Test run_all returns dict with counts."""
        pruner = DataPruner()
        
        result = pruner.run_all()
        
        assert "metrics_pruned" in result
        assert "models_marked_inactive" in result

    @patch("orchestrator.resilience.DataPruner.prune_metrics")
    @patch("orchestrator.resilience.DataPruner.prune_inactive_models")
    def test_run_all_calls_both(
        self, mock_inactive: MagicMock, mock_metrics: MagicMock
    ) -> None:
        """Test run_all calls both pruning methods."""
        mock_metrics.return_value = 10
        mock_inactive.return_value = 2
        
        pruner = DataPruner()
        result = pruner.run_all()
        
        assert result["metrics_pruned"] == 10
        assert result["models_marked_inactive"] == 2
        mock_metrics.assert_called_once()
        mock_inactive.assert_called_once()
