"""Resilience utilities: offline cache and data pruning."""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from orchestrator.config import settings

logger = logging.getLogger(__name__)


# --- T-039: Offline Mode ---


@dataclass
class CachedResponse:
    """Cached adapter response."""

    source: str
    """Source adapter name (e.g., 'openrouter', 'lmsys')."""

    data: Any
    """Cached response data."""

    timestamp: str
    """ISO format timestamp when cached."""

    @property
    def cached_at(self) -> datetime:
        """Get timestamp as datetime."""
        return datetime.fromisoformat(self.timestamp)

    @property
    def age_seconds(self) -> float:
        """Get age of cache in seconds."""
        return (datetime.utcnow() - self.cached_at).total_seconds()

    def is_stale(self, max_age_hours: float = 24) -> bool:
        """Check if cache is older than max age."""
        max_age_seconds = max_age_hours * 3600
        return self.age_seconds > max_age_seconds


class OfflineCache:
    """
    Cache for adapter responses to enable offline fallback.

    Stores last known good data from adapters and serves
    cached responses when live fetches fail.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        default_max_age_hours: float = 24,
    ) -> None:
        """
        Initialize offline cache.

        Args:
            cache_dir: Directory to store cache files
            default_max_age_hours: Default cache staleness threshold
        """
        self._cache_dir = cache_dir or settings.data_dir / "cache"
        self._default_max_age = default_max_age_hours
        self._memory_cache: dict[str, CachedResponse] = {}

        # Ensure cache directory exists
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_file(self, source: str) -> Path:
        """Get cache file path for a source."""
        safe_name = source.replace("/", "_").replace("\\", "_")
        return self._cache_dir / f"{safe_name}.json"

    def store(self, source: str, data: Any) -> None:
        """
        Store response data in cache.

        Args:
            source: Source adapter name
            data: Response data to cache
        """
        cached = CachedResponse(
            source=source,
            data=data,
            timestamp=datetime.utcnow().isoformat(),
        )

        # Store in memory
        self._memory_cache[source] = cached

        # Persist to disk
        try:
            cache_file = self._get_cache_file(source)
            with open(cache_file, "w") as f:
                json.dump(asdict(cached), f, indent=2, default=str)
            logger.debug(f"Cached response for {source}")
        except Exception as e:
            logger.warning(f"Failed to persist cache for {source}: {e}")

    def retrieve(
        self,
        source: str,
        max_age_hours: float | None = None,
    ) -> CachedResponse | None:
        """
        Retrieve cached response.

        Args:
            source: Source adapter name
            max_age_hours: Maximum acceptable cache age

        Returns:
            CachedResponse or None if not found/too old
        """
        max_age = max_age_hours or self._default_max_age

        # Try memory cache first
        if source in self._memory_cache:
            cached = self._memory_cache[source]
            if not cached.is_stale(max_age):
                return cached
            logger.debug(f"Memory cache for {source} is stale")

        # Try disk cache
        try:
            cache_file = self._get_cache_file(source)
            if cache_file.exists():
                with open(cache_file) as f:
                    data = json.load(f)
                    cached = CachedResponse(**data)

                    if not cached.is_stale(max_age):
                        # Update memory cache
                        self._memory_cache[source] = cached
                        return cached
                    logger.debug(f"Disk cache for {source} is stale")
        except Exception as e:
            logger.warning(f"Failed to load cache for {source}: {e}")

        return None

    def retrieve_stale(self, source: str) -> CachedResponse | None:
        """
        Retrieve cached response even if stale.

        Use when live fetch fails and any cached data is better than none.
        """
        # Try memory cache
        if source in self._memory_cache:
            cached = self._memory_cache[source]
            logger.warning(
                f"Serving stale cached data for {source} "
                f"(age: {cached.age_seconds / 3600:.1f}h)"
            )
            return cached

        # Try disk cache
        try:
            cache_file = self._get_cache_file(source)
            if cache_file.exists():
                with open(cache_file) as f:
                    data = json.load(f)
                    cached = CachedResponse(**data)
                    logger.warning(
                        f"Serving stale cached data for {source} "
                        f"(age: {cached.age_seconds / 3600:.1f}h)"
                    )
                    return cached
        except Exception as e:
            logger.error(f"Failed to load stale cache for {source}: {e}")

        return None

    def clear(self, source: str | None = None) -> None:
        """
        Clear cache.

        Args:
            source: Specific source to clear, or None for all
        """
        if source:
            self._memory_cache.pop(source, None)
            cache_file = self._get_cache_file(source)
            if cache_file.exists():
                cache_file.unlink()
            logger.info(f"Cleared cache for {source}")
        else:
            self._memory_cache.clear()
            for cache_file in self._cache_dir.glob("*.json"):
                cache_file.unlink()
            logger.info("Cleared all cache")


# Default cache instance
default_offline_cache = OfflineCache()


# --- T-040: Data Pruning Job ---


class DataPruner:
    """
    Cleans old metrics from the database.

    Runs as a scheduled job to prevent unbounded data growth.
    """

    def __init__(
        self,
        retention_days: int = 30,
        db_manager: Any = None,
    ) -> None:
        """
        Initialize data pruner.

        Args:
            retention_days: Days to retain metrics
            db_manager: Database manager instance
        """
        self._retention_days = retention_days
        self._db_manager = db_manager

    def set_db_manager(self, db_manager: Any) -> None:
        """Set database manager (for deferred initialization)."""
        self._db_manager = db_manager

    def prune_metrics(self) -> int:
        """
        Delete metrics older than retention period.

        Returns:
            Number of deleted records
        """
        if self._db_manager is None:
            logger.error("DataPruner: No database manager configured")
            return 0

        from orchestrator.db.models import Metric

        cutoff = datetime.utcnow() - timedelta(days=self._retention_days)

        try:
            with self._db_manager.get_session() as session:
                # Count before delete
                count = session.query(Metric).filter(
                    Metric.timestamp < cutoff
                ).count()

                if count > 0:
                    # Delete old metrics
                    session.query(Metric).filter(
                        Metric.timestamp < cutoff
                    ).delete(synchronize_session=False)

                    logger.info(
                        f"Pruned {count} metrics older than {self._retention_days} days"
                    )
                else:
                    logger.debug("No metrics to prune")

                return count

        except Exception as e:
            logger.error(f"Failed to prune metrics: {e}")
            return 0

    def prune_inactive_models(self, days_inactive: int = 90) -> int:
        """
        Mark models as inactive if not updated recently.

        Args:
            days_inactive: Days without metrics to consider inactive

        Returns:
            Number of models marked inactive
        """
        if self._db_manager is None:
            logger.error("DataPruner: No database manager configured")
            return 0

        from sqlalchemy import func
        from orchestrator.db.models import Metric, Model

        cutoff = datetime.utcnow() - timedelta(days=days_inactive)

        try:
            with self._db_manager.get_session() as session:
                # Find models with no recent metrics
                subquery = (
                    session.query(Metric.model_id)
                    .filter(Metric.timestamp >= cutoff)
                    .distinct()
                    .subquery()
                )

                # Update models not in subquery
                count = (
                    session.query(Model)
                    .filter(Model.active == True)
                    .filter(Model.id.notin_(session.query(subquery)))
                    .update({Model.active: False}, synchronize_session=False)
                )

                if count > 0:
                    logger.info(f"Marked {count} models as inactive")

                return count

        except Exception as e:
            logger.error(f"Failed to mark models inactive: {e}")
            return 0

    def run_all(self) -> dict[str, int]:
        """
        Run all pruning tasks.

        Returns:
            Dict with counts for each pruning operation
        """
        return {
            "metrics_pruned": self.prune_metrics(),
            "models_marked_inactive": self.prune_inactive_models(),
        }


# Default pruner instance
default_data_pruner = DataPruner(
    retention_days=getattr(settings, "metric_retention_days", 30)
)
