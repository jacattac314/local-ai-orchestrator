"""
Analytics event collector.
Records routing decisions, API calls, and usage metrics.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import logging

from .storage import AnalyticsStorage


logger = logging.getLogger(__name__)


@dataclass
class RoutingEvent:
    """A single routing decision event."""
    
    timestamp: datetime
    model_selected: str
    profile_used: str
    routing_time_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    was_fallback: bool = False
    success: bool = True
    error_message: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "model_selected": self.model_selected,
            "profile_used": self.profile_used,
            "routing_time_ms": self.routing_time_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": self.estimated_cost,
            "was_fallback": self.was_fallback,
            "success": self.success,
            "error_message": self.error_message,
        }


@dataclass
class AnalyticsCollector:
    """
    Collects and stores analytics events.
    
    Thread-safe event collection with buffered writes.
    """
    
    storage: Optional[AnalyticsStorage] = None
    buffer: list[RoutingEvent] = field(default_factory=list)
    buffer_size: int = 100
    _initialized: bool = False
    
    def initialize(self, db_path: str = "analytics.db") -> None:
        """Initialize the analytics storage."""
        if not self._initialized:
            self.storage = AnalyticsStorage(db_path)
            self._initialized = True
            logger.info(f"Analytics initialized with storage: {db_path}")
    
    def record_routing(
        self,
        model_selected: str,
        profile_used: str,
        routing_time_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        estimated_cost: float = 0.0,
        was_fallback: bool = False,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """Record a routing decision event."""
        event = RoutingEvent(
            timestamp=datetime.utcnow(),
            model_selected=model_selected,
            profile_used=profile_used,
            routing_time_ms=routing_time_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            estimated_cost=estimated_cost,
            was_fallback=was_fallback,
            success=success,
            error_message=error_message,
        )
        
        self.buffer.append(event)
        
        # Flush buffer if full
        if len(self.buffer) >= self.buffer_size:
            self.flush()
    
    def flush(self) -> None:
        """Write buffered events to storage."""
        if not self.buffer:
            return
        
        if self.storage:
            try:
                self.storage.insert_events(self.buffer)
                logger.debug(f"Flushed {len(self.buffer)} analytics events")
            except Exception as e:
                logger.error(f"Failed to flush analytics: {e}")
        
        self.buffer.clear()
    
    def get_summary(self, period_hours: int = 24) -> dict:
        """Get analytics summary for the specified period."""
        self.flush()  # Ensure all events are persisted
        
        if not self.storage:
            return self._empty_summary()
        
        return self.storage.get_summary(period_hours)
    
    def get_usage_timeseries(
        self,
        period_hours: int = 24,
        bucket_minutes: int = 60,
    ) -> list[dict]:
        """Get time-series usage data."""
        self.flush()
        
        if not self.storage:
            return []
        
        return self.storage.get_timeseries(period_hours, bucket_minutes)
    
    def get_model_breakdown(self, period_hours: int = 24) -> list[dict]:
        """Get per-model usage breakdown."""
        self.flush()
        
        if not self.storage:
            return []
        
        return self.storage.get_model_breakdown(period_hours)
    
    def _empty_summary(self) -> dict:
        return {
            "total_requests": 0,
            "total_tokens": 0,
            "estimated_cost": 0.0,
            "avg_latency_ms": 0.0,
            "success_rate": 1.0,
            "top_models": [],
            "requests_by_profile": {},
        }


# Global default collector instance
default_collector = AnalyticsCollector()
