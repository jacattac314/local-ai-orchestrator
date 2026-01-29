"""
Analytics SQLite storage.
Persists usage events and provides aggregation queries.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from .collector import RoutingEvent


logger = logging.getLogger(__name__)


class AnalyticsStorage:
    """
    SQLite storage for analytics events.
    
    Handles persistence and aggregation queries.
    """
    
    def __init__(self, db_path: str = "analytics.db"):
        self.db_path = Path(db_path)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS routing_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    model_selected TEXT NOT NULL,
                    profile_used TEXT NOT NULL,
                    routing_time_ms REAL NOT NULL,
                    prompt_tokens INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    estimated_cost REAL DEFAULT 0.0,
                    was_fallback INTEGER DEFAULT 0,
                    success INTEGER DEFAULT 1,
                    error_message TEXT
                )
            """)
            
            # Create indexes for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_timestamp 
                ON routing_events(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_model 
                ON routing_events(model_selected)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_profile 
                ON routing_events(profile_used)
            """)
            
            conn.commit()
    
    def insert_events(self, events: list["RoutingEvent"]) -> None:
        """Insert multiple events in a batch."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT INTO routing_events (
                    timestamp, model_selected, profile_used, routing_time_ms,
                    prompt_tokens, completion_tokens, total_tokens,
                    estimated_cost, was_fallback, success, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        e.timestamp.isoformat(),
                        e.model_selected,
                        e.profile_used,
                        e.routing_time_ms,
                        e.prompt_tokens,
                        e.completion_tokens,
                        e.total_tokens,
                        e.estimated_cost,
                        1 if e.was_fallback else 0,
                        1 if e.success else 0,
                        e.error_message,
                    )
                    for e in events
                ],
            )
            conn.commit()
    
    def get_summary(self, period_hours: int = 24) -> dict:
        """Get analytics summary for the specified period."""
        cutoff = (datetime.utcnow() - timedelta(hours=period_hours)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Overall stats
            row = conn.execute(
                """
                SELECT 
                    COUNT(*) as total_requests,
                    COALESCE(SUM(total_tokens), 0) as total_tokens,
                    COALESCE(SUM(estimated_cost), 0) as estimated_cost,
                    COALESCE(AVG(routing_time_ms), 0) as avg_latency_ms,
                    COALESCE(AVG(success), 1) as success_rate
                FROM routing_events
                WHERE timestamp >= ?
                """,
                (cutoff,),
            ).fetchone()
            
            # Top models
            top_models = conn.execute(
                """
                SELECT 
                    model_selected as model,
                    COUNT(*) as count,
                    SUM(total_tokens) as tokens,
                    SUM(estimated_cost) as cost
                FROM routing_events
                WHERE timestamp >= ?
                GROUP BY model_selected
                ORDER BY count DESC
                LIMIT 10
                """,
                (cutoff,),
            ).fetchall()
            
            # Requests by profile
            profile_counts = conn.execute(
                """
                SELECT profile_used, COUNT(*) as count
                FROM routing_events
                WHERE timestamp >= ?
                GROUP BY profile_used
                """,
                (cutoff,),
            ).fetchall()
            
            return {
                "total_requests": row["total_requests"],
                "total_tokens": row["total_tokens"],
                "estimated_cost": round(row["estimated_cost"], 4),
                "avg_latency_ms": round(row["avg_latency_ms"], 2),
                "success_rate": round(row["success_rate"], 4),
                "top_models": [
                    {
                        "model": m["model"],
                        "count": m["count"],
                        "tokens": m["tokens"],
                        "cost": round(m["cost"], 4),
                    }
                    for m in top_models
                ],
                "requests_by_profile": {
                    p["profile_used"]: p["count"] for p in profile_counts
                },
            }
    
    def get_timeseries(
        self,
        period_hours: int = 24,
        bucket_minutes: int = 60,
    ) -> list[dict]:
        """Get time-series data with bucketed aggregation."""
        cutoff = (datetime.utcnow() - timedelta(hours=period_hours)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # SQLite doesn't have great time bucketing, so we'll do it in Python
            rows = conn.execute(
                """
                SELECT 
                    timestamp,
                    total_tokens,
                    estimated_cost,
                    routing_time_ms,
                    success
                FROM routing_events
                WHERE timestamp >= ?
                ORDER BY timestamp
                """,
                (cutoff,),
            ).fetchall()
        
        if not rows:
            return []
        
        # Bucket the data
        buckets: dict[str, dict] = {}
        bucket_delta = timedelta(minutes=bucket_minutes)
        
        for row in rows:
            ts = datetime.fromisoformat(row["timestamp"])
            bucket_start = ts.replace(
                minute=(ts.minute // bucket_minutes) * bucket_minutes,
                second=0,
                microsecond=0,
            )
            bucket_key = bucket_start.isoformat()
            
            if bucket_key not in buckets:
                buckets[bucket_key] = {
                    "timestamp": bucket_key,
                    "requests": 0,
                    "tokens": 0,
                    "cost": 0.0,
                    "avg_latency_ms": 0.0,
                    "_latency_sum": 0.0,
                }
            
            buckets[bucket_key]["requests"] += 1
            buckets[bucket_key]["tokens"] += row["total_tokens"]
            buckets[bucket_key]["cost"] += row["estimated_cost"]
            buckets[bucket_key]["_latency_sum"] += row["routing_time_ms"]
        
        # Calculate averages and format
        result = []
        for bucket in sorted(buckets.values(), key=lambda x: x["timestamp"]):
            if bucket["requests"] > 0:
                bucket["avg_latency_ms"] = round(
                    bucket["_latency_sum"] / bucket["requests"], 2
                )
            del bucket["_latency_sum"]
            bucket["cost"] = round(bucket["cost"], 4)
            result.append(bucket)
        
        return result
    
    def get_model_breakdown(self, period_hours: int = 24) -> list[dict]:
        """Get detailed per-model statistics."""
        cutoff = (datetime.utcnow() - timedelta(hours=period_hours)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            rows = conn.execute(
                """
                SELECT 
                    model_selected as model,
                    COUNT(*) as requests,
                    SUM(total_tokens) as total_tokens,
                    SUM(prompt_tokens) as prompt_tokens,
                    SUM(completion_tokens) as completion_tokens,
                    SUM(estimated_cost) as cost,
                    AVG(routing_time_ms) as avg_latency_ms,
                    AVG(success) as success_rate,
                    SUM(was_fallback) as fallback_count
                FROM routing_events
                WHERE timestamp >= ?
                GROUP BY model_selected
                ORDER BY requests DESC
                """,
                (cutoff,),
            ).fetchall()
            
            return [
                {
                    "model": row["model"],
                    "requests": row["requests"],
                    "total_tokens": row["total_tokens"],
                    "prompt_tokens": row["prompt_tokens"],
                    "completion_tokens": row["completion_tokens"],
                    "cost": round(row["cost"], 4),
                    "avg_latency_ms": round(row["avg_latency_ms"], 2),
                    "success_rate": round(row["success_rate"], 4),
                    "fallback_count": row["fallback_count"],
                }
                for row in rows
            ]
    
    def prune_old_events(self, keep_days: int = 30) -> int:
        """Delete events older than the specified number of days."""
        cutoff = (datetime.utcnow() - timedelta(days=keep_days)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM routing_events WHERE timestamp < ?",
                (cutoff,),
            )
            conn.commit()
            return cursor.rowcount
