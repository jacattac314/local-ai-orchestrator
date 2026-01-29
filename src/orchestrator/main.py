"""Main entry point for the orchestrator application."""

import logging
import signal
import sys
from typing import NoReturn

from orchestrator.adapters.openrouter import OpenRouterAdapter
from orchestrator.config import settings
from orchestrator.db import DatabaseManager
from orchestrator.scheduler import SchedulerService

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class Orchestrator:
    """Main orchestrator application coordinating all services."""

    def __init__(self) -> None:
        """Initialize the orchestrator."""
        self.db_manager = DatabaseManager(database_url=settings.database_url)
        self.scheduler = SchedulerService(
            database_url=settings.scheduler_database_url,
            max_workers=settings.scheduler_max_workers,
            timezone=settings.scheduler_timezone,
        )
        self.openrouter_adapter = OpenRouterAdapter(
            api_key=settings.openrouter_api_key
        )

    def _handle_openrouter_sync(self) -> None:
        """Sync job callback for OpenRouter data."""
        logger.info("Running OpenRouter sync job...")
        try:
            metrics = self.openrouter_adapter.fetch_and_parse_sync()
            logger.info(f"Fetched {len(metrics)} metrics from OpenRouter")
            self._persist_metrics(metrics)
        except Exception as e:
            logger.error(f"OpenRouter sync failed: {e}")

    def _persist_metrics(self, metrics: list) -> None:
        """Persist metrics to database."""
        from datetime import datetime

        from orchestrator.db.models import Metric, Model

        with self.db_manager.get_session() as session:
            # Group metrics by model
            model_metrics: dict[str, list] = {}
            for metric in metrics:
                if metric.model_name not in model_metrics:
                    model_metrics[metric.model_name] = []
                model_metrics[metric.model_name].append(metric)

            for model_name, model_metrics_list in model_metrics.items():
                # Get or create model
                model = session.query(Model).filter_by(name=model_name).first()
                if not model:
                    # Extract provider from model ID (e.g., "openai/gpt-4" -> "openai")
                    provider = model_name.split("/")[0] if "/" in model_name else "unknown"
                    context_length = None
                    for m in model_metrics_list:
                        if m.metric_type == "context_length":
                            context_length = int(m.value)
                            break

                    model = Model(
                        name=model_name,
                        provider=provider,
                        context_length=context_length,
                        active=True,
                    )
                    session.add(model)
                    session.flush()

                # Add metrics
                for raw_metric in model_metrics_list:
                    if raw_metric.metric_type == "context_length":
                        continue  # Skip, already handled

                    metric = Metric(
                        model_id=model.id,
                        source=raw_metric.source,
                        metric_type=raw_metric.metric_type,
                        value=raw_metric.value,
                        timestamp=raw_metric.timestamp,
                    )
                    session.add(metric)

            logger.info(f"Persisted metrics for {len(model_metrics)} models")

    def start(self) -> None:
        """Start the orchestrator services."""
        logger.info("Starting Local AI Orchestrator...")

        # Initialize database
        self.db_manager.init_db()
        logger.info("Database initialized")

        # Register sync jobs
        self.scheduler.add_job(
            job_id="openrouter_sync",
            func=self._handle_openrouter_sync,
            interval_minutes=settings.openrouter_sync_interval,
            run_immediately=True,
        )
        logger.info(f"OpenRouter sync job registered ({settings.openrouter_sync_interval}m interval)")

        # Register data pruning job (T-040)
        from orchestrator.resilience import default_data_pruner
        default_data_pruner.set_db_manager(self.db_manager)
        self.scheduler.add_job(
            job_id="data_pruning",
            func=default_data_pruner.run_all,
            interval_minutes=settings.data_pruning_interval,
            run_immediately=False,  # Don't prune on startup
        )
        logger.info(f"Data pruning job registered ({settings.data_pruning_interval}m interval)")

        # Start scheduler
        self.scheduler.start()
        logger.info("Scheduler started")

    def stop(self) -> None:
        """Stop all services gracefully."""
        logger.info("Stopping orchestrator...")
        self.scheduler.shutdown(wait=True)
        self.db_manager.close()
        logger.info("Orchestrator stopped")


def main() -> NoReturn:
    """Main entry point."""
    orchestrator = Orchestrator()

    # Handle graceful shutdown
    def signal_handler(signum: int, frame: object) -> None:
        logger.info(f"Received signal {signum}")
        orchestrator.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        orchestrator.start()
        # Keep running
        logger.info("Orchestrator running. Press Ctrl+C to stop.")
        signal.pause()  # Wait for signals
    except AttributeError:
        # signal.pause() not available on Windows
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        orchestrator.stop()
    
    sys.exit(0)


if __name__ == "__main__":
    main()
