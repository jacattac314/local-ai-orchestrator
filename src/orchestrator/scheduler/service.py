"""APScheduler-based background job service."""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable

from apscheduler.executors.pool import ThreadPoolExecutor as APSThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Background job scheduler with persistence.

    Uses APScheduler with SQLAlchemy job store for persistent job tracking
    and a thread pool executor for concurrent job execution.
    """

    def __init__(
        self,
        database_url: str = "sqlite:///data/scheduler.db",
        max_workers: int = 4,
        timezone: str = "UTC",
    ) -> None:
        """
        Initialize the scheduler service.

        Args:
            database_url: SQLAlchemy URL for job persistence
            max_workers: Maximum concurrent jobs
            timezone: Scheduler timezone
        """
        self._database_url = database_url
        self._max_workers = max_workers
        self._timezone = timezone
        self._scheduler: BackgroundScheduler | None = None
        self._executor: ThreadPoolExecutor | None = None

    @property
    def scheduler(self) -> BackgroundScheduler:
        """Get or create the scheduler instance."""
        if self._scheduler is None:
            self._scheduler = self._create_scheduler()
        return self._scheduler

    def _create_scheduler(self) -> BackgroundScheduler:
        """Create and configure the APScheduler instance."""
        jobstores = {
            "default": SQLAlchemyJobStore(url=self._database_url),
        }

        executors = {
            "default": APSThreadPoolExecutor(max_workers=self._max_workers),
        }

        job_defaults = {
            "coalesce": True,  # Combine missed runs into one
            "max_instances": 1,  # Prevent overlapping runs
            "misfire_grace_time": 60 * 5,  # 5 minute grace period
        }

        scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=self._timezone,
        )

        logger.info(
            f"Scheduler configured with {self._max_workers} workers, "
            f"timezone={self._timezone}"
        )
        return scheduler

    def start(self) -> None:
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")
        else:
            logger.warning("Scheduler is already running")

    def shutdown(self, wait: bool = True) -> None:
        """
        Shutdown the scheduler.

        Args:
            wait: Wait for running jobs to complete
        """
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("Scheduler shutdown complete")

    def add_job(
        self,
        job_id: str,
        func: Callable[..., Any],
        interval_minutes: int,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        run_immediately: bool = False,
    ) -> None:
        """
        Add an interval-based job to the scheduler.

        Args:
            job_id: Unique identifier for the job
            func: Function to execute
            interval_minutes: Minutes between runs
            args: Positional arguments for the function
            kwargs: Keyword arguments for the function
            run_immediately: Run the job immediately after adding
        """
        trigger = IntervalTrigger(minutes=interval_minutes)

        # Remove existing job if it exists
        self.remove_job(job_id)

        self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            name=job_id,
            args=args or (),
            kwargs=kwargs or {},
            replace_existing=True,
        )

        logger.info(f"Job '{job_id}' added with {interval_minutes}m interval")

        if run_immediately:
            self.run_job_now(job_id)

    def remove_job(self, job_id: str) -> bool:
        """
        Remove a job from the scheduler.

        Args:
            job_id: Unique identifier of the job to remove

        Returns:
            True if job was removed, False if not found
        """
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Job '{job_id}' removed")
            return True
        except Exception:
            return False

    def run_job_now(self, job_id: str) -> None:
        """
        Trigger immediate execution of a job.

        Args:
            job_id: Unique identifier of the job
        """
        job = self.scheduler.get_job(job_id)
        if job:
            job.modify(next_run_time=datetime.now())
            logger.info(f"Job '{job_id}' triggered for immediate execution")
        else:
            logger.warning(f"Job '{job_id}' not found")

    def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        """
        Get the status of a job.

        Args:
            job_id: Unique identifier of the job

        Returns:
            Job status dict or None if not found
        """
        job = self.scheduler.get_job(job_id)
        if job:
            return {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time,
                "pending": job.pending,
            }
        return None

    def list_jobs(self) -> list[dict[str, Any]]:
        """
        List all scheduled jobs.

        Returns:
            List of job status dicts
        """
        jobs = self.scheduler.get_jobs()
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time,
                "pending": job.pending,
            }
            for job in jobs
        ]

    def pause_job(self, job_id: str) -> bool:
        """Pause a job."""
        try:
            self.scheduler.pause_job(job_id)
            logger.info(f"Job '{job_id}' paused")
            return True
        except Exception:
            return False

    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job."""
        try:
            self.scheduler.resume_job(job_id)
            logger.info(f"Job '{job_id}' resumed")
            return True
        except Exception:
            return False

    @property
    def is_running(self) -> bool:
        """Check if the scheduler is running."""
        return self._scheduler is not None and self._scheduler.running
