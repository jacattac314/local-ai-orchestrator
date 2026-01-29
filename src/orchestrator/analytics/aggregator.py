"""
Analytics aggregator utilities.
Helper functions for computing derived metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class UsageStats:
    """Aggregated usage statistics."""
    
    period_start: datetime
    period_end: datetime
    total_requests: int
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    estimated_cost: float
    avg_latency_ms: float
    success_rate: float
    requests_per_hour: float
    tokens_per_request: float
    cost_per_request: float


class AnalyticsAggregator:
    """
    Computes derived metrics from raw analytics data.
    """
    
    @staticmethod
    def compute_stats(summary: dict, period_hours: int) -> UsageStats:
        """Compute derived statistics from a summary."""
        now = datetime.utcnow()
        total_requests = summary.get("total_requests", 0)
        total_tokens = summary.get("total_tokens", 0)
        estimated_cost = summary.get("estimated_cost", 0.0)
        
        return UsageStats(
            period_start=now - timedelta(hours=period_hours),
            period_end=now,
            total_requests=total_requests,
            total_tokens=total_tokens,
            prompt_tokens=0,  # Not tracked in summary
            completion_tokens=0,
            estimated_cost=estimated_cost,
            avg_latency_ms=summary.get("avg_latency_ms", 0.0),
            success_rate=summary.get("success_rate", 1.0),
            requests_per_hour=total_requests / period_hours if period_hours > 0 else 0,
            tokens_per_request=total_tokens / total_requests if total_requests > 0 else 0,
            cost_per_request=estimated_cost / total_requests if total_requests > 0 else 0,
        )
    
    @staticmethod
    def estimate_monthly_cost(
        daily_cost: float,
        growth_rate: float = 0.0,
    ) -> dict:
        """
        Estimate monthly costs based on daily usage.
        
        Args:
            daily_cost: Current daily cost
            growth_rate: Expected daily growth rate (0.0 to 1.0)
            
        Returns:
            Dict with projections
        """
        base_monthly = daily_cost * 30
        
        # Compound growth projection
        if growth_rate > 0:
            projected = sum(
                daily_cost * ((1 + growth_rate) ** day)
                for day in range(30)
            )
        else:
            projected = base_monthly
        
        return {
            "base_monthly": round(base_monthly, 2),
            "projected_monthly": round(projected, 2),
            "daily_average": round(daily_cost, 4),
            "growth_rate": growth_rate,
        }
    
    @staticmethod
    def compute_efficiency_score(
        quality_score: float,
        cost_per_request: float,
        latency_ms: float,
        baseline_cost: float = 0.01,
        baseline_latency: float = 500,
    ) -> float:
        """
        Compute an efficiency score balancing quality vs cost/latency.
        
        Higher is better. Normalized to 0-1 range.
        """
        if cost_per_request <= 0 or latency_ms <= 0:
            return 0.0
        
        cost_efficiency = min(baseline_cost / cost_per_request, 2.0) / 2.0
        latency_efficiency = min(baseline_latency / latency_ms, 2.0) / 2.0
        
        # Weight: 50% quality, 25% cost efficiency, 25% latency efficiency
        score = (
            quality_score * 0.5 +
            cost_efficiency * 0.25 +
            latency_efficiency * 0.25
        )
        
        return min(max(score, 0.0), 1.0)
    
    @staticmethod
    def identify_anomalies(
        timeseries: list[dict],
        threshold_std: float = 2.0,
    ) -> list[dict]:
        """
        Identify anomalous time buckets based on request volume.
        
        Returns buckets that deviate significantly from the mean.
        """
        if len(timeseries) < 5:
            return []
        
        requests = [b["requests"] for b in timeseries]
        mean_requests = sum(requests) / len(requests)
        
        if mean_requests == 0:
            return []
        
        variance = sum((r - mean_requests) ** 2 for r in requests) / len(requests)
        std_dev = variance ** 0.5
        
        if std_dev == 0:
            return []
        
        anomalies = []
        for bucket in timeseries:
            z_score = (bucket["requests"] - mean_requests) / std_dev
            if abs(z_score) > threshold_std:
                anomalies.append({
                    **bucket,
                    "z_score": round(z_score, 2),
                    "anomaly_type": "spike" if z_score > 0 else "drop",
                })
        
        return anomalies
