"""Configuration module using Pydantic Settings."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "sqlite:///data/orchestrator.db"
    scheduler_database_url: str = "sqlite:///data/scheduler.db"

    # API Keys
    openrouter_api_key: str | None = None

    # Scheduler
    scheduler_timezone: str = "UTC"
    scheduler_max_workers: int = 4

    # Sync intervals (minutes)
    openrouter_sync_interval: int = 5
    lmsys_sync_interval: int = 360  # 6 hours
    huggingface_sync_interval: int = 1440  # 24 hours

    # HTTP Client
    http_timeout_connect: float = 10.0
    http_timeout_read: float = 30.0
    http_max_retries: int = 3

    # Logging
    log_level: str = "INFO"

    # API Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Security (T-037, T-038)
    api_key: str | None = None  # Optional API authentication
    allowed_domains: list[str] = []  # URL validation allowlist (empty = allow all external)

    # Resilience (T-039, T-040)
    offline_mode_enabled: bool = True  # Enable offline cache fallback
    metric_retention_days: int = 30  # Days to keep metrics before pruning
    data_pruning_interval: int = 1440  # Run pruning job every 24 hours (minutes)

    # Redis Cache
    redis_url: str | None = None  # Redis connection URL (e.g., redis://localhost:6379/0)
    redis_ttl_seconds: int = 3600  # Default cache TTL (1 hour)
    redis_prefix: str = "orchestrator:"  # Key prefix for namespacing
    cache_backend: str = "memory"  # Cache backend: "memory" or "redis"

    @property
    def data_dir(self) -> Path:
        """Get the data directory path."""
        # Extract path from SQLite URL
        if self.database_url.startswith("sqlite:///"):
            db_path = Path(self.database_url.replace("sqlite:///", ""))
            return db_path.parent
        return Path("data")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience function for quick access
settings = get_settings()
