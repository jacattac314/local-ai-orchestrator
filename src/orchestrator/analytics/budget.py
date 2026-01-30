"""
Budget management service.
Tracks spending and enforces configurable budget limits.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .storage import AnalyticsStorage


logger = logging.getLogger(__name__)


class BudgetPeriod(str, Enum):
    """Budget period types."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class BudgetStatus(str, Enum):
    """Current budget status."""
    OK = "ok"
    WARNING = "warning"  # Approaching limit
    EXCEEDED = "exceeded"


@dataclass
class BudgetConfig:
    """
    Budget configuration and limits.
    
    All limits are in USD. Set to 0 to disable a limit.
    """
    
    daily_limit: float = 10.0
    weekly_limit: float = 50.0
    monthly_limit: float = 100.0
    alert_threshold: float = 0.8  # Alert at 80% of limit
    hard_limit: bool = False  # If True, block requests when exceeded
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "BudgetConfig":
        return cls(
            daily_limit=data.get("daily_limit", 10.0),
            weekly_limit=data.get("weekly_limit", 50.0),
            monthly_limit=data.get("monthly_limit", 100.0),
            alert_threshold=data.get("alert_threshold", 0.8),
            hard_limit=data.get("hard_limit", False),
        )


@dataclass
class SpendSummary:
    """Current spending summary."""
    
    daily_spend: float = 0.0
    weekly_spend: float = 0.0
    monthly_spend: float = 0.0
    daily_remaining: float = 0.0
    weekly_remaining: float = 0.0
    monthly_remaining: float = 0.0
    daily_percent: float = 0.0
    weekly_percent: float = 0.0
    monthly_percent: float = 0.0
    status: BudgetStatus = BudgetStatus.OK
    status_message: str = ""
    
    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "status": self.status.value,
        }


@dataclass
class BudgetManager:
    """
    Manages budget limits and spending tracking.
    
    Integrates with AnalyticsStorage to query actual spend.
    """
    
    storage: Optional["AnalyticsStorage"] = None
    config: BudgetConfig = field(default_factory=BudgetConfig)
    config_path: str = "budget_config.json"
    _initialized: bool = False
    
    def initialize(self, storage: "AnalyticsStorage", config_path: str = "budget_config.json") -> None:
        """Initialize with storage backend and load config."""
        self.storage = storage
        self.config_path = config_path
        self._load_config()
        self._initialized = True
        logger.info(f"Budget manager initialized: daily=${self.config.daily_limit}, weekly=${self.config.weekly_limit}, monthly=${self.config.monthly_limit}")
    
    def _load_config(self) -> None:
        """Load configuration from file."""
        path = Path(self.config_path)
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                self.config = BudgetConfig.from_dict(data)
                logger.info(f"Loaded budget config from {self.config_path}")
            except Exception as e:
                logger.warning(f"Failed to load budget config: {e}, using defaults")
                self.config = BudgetConfig()
        else:
            self.config = BudgetConfig()
    
    def save_config(self) -> None:
        """Persist configuration to file."""
        path = Path(self.config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w") as f:
            json.dump(self.config.to_dict(), f, indent=2)
        
        logger.info(f"Saved budget config to {self.config_path}")
    
    def update_config(
        self,
        daily_limit: Optional[float] = None,
        weekly_limit: Optional[float] = None,
        monthly_limit: Optional[float] = None,
        alert_threshold: Optional[float] = None,
        hard_limit: Optional[bool] = None,
    ) -> BudgetConfig:
        """Update budget configuration."""
        if daily_limit is not None:
            self.config.daily_limit = max(0.0, daily_limit)
        if weekly_limit is not None:
            self.config.weekly_limit = max(0.0, weekly_limit)
        if monthly_limit is not None:
            self.config.monthly_limit = max(0.0, monthly_limit)
        if alert_threshold is not None:
            self.config.alert_threshold = max(0.0, min(1.0, alert_threshold))
        if hard_limit is not None:
            self.config.hard_limit = hard_limit
        
        self.save_config()
        return self.config
    
    def get_spend_summary(self) -> SpendSummary:
        """
        Get current spending summary with status.
        
        Returns spending for each period and calculates remaining budget.
        """
        if not self.storage:
            return SpendSummary()
        
        # Get spend for each period
        daily_spend = self._get_period_spend(hours=24)
        weekly_spend = self._get_period_spend(hours=168)  # 7 days
        monthly_spend = self._get_period_spend(hours=720)  # 30 days
        
        # Calculate remaining and percentages
        daily_remaining = max(0, self.config.daily_limit - daily_spend)
        weekly_remaining = max(0, self.config.weekly_limit - weekly_spend)
        monthly_remaining = max(0, self.config.monthly_limit - monthly_spend)
        
        daily_percent = (daily_spend / self.config.daily_limit * 100) if self.config.daily_limit > 0 else 0
        weekly_percent = (weekly_spend / self.config.weekly_limit * 100) if self.config.weekly_limit > 0 else 0
        monthly_percent = (monthly_spend / self.config.monthly_limit * 100) if self.config.monthly_limit > 0 else 0
        
        # Determine status
        status = BudgetStatus.OK
        status_message = "Budget healthy"
        
        # Check for exceeded limits
        exceeded = []
        if self.config.daily_limit > 0 and daily_spend >= self.config.daily_limit:
            exceeded.append("daily")
        if self.config.weekly_limit > 0 and weekly_spend >= self.config.weekly_limit:
            exceeded.append("weekly")
        if self.config.monthly_limit > 0 and monthly_spend >= self.config.monthly_limit:
            exceeded.append("monthly")
        
        if exceeded:
            status = BudgetStatus.EXCEEDED
            status_message = f"Budget exceeded: {', '.join(exceeded)}"
        else:
            # Check for warning thresholds
            warnings = []
            threshold = self.config.alert_threshold
            if self.config.daily_limit > 0 and daily_percent >= threshold * 100:
                warnings.append(f"daily ({daily_percent:.0f}%)")
            if self.config.weekly_limit > 0 and weekly_percent >= threshold * 100:
                warnings.append(f"weekly ({weekly_percent:.0f}%)")
            if self.config.monthly_limit > 0 and monthly_percent >= threshold * 100:
                warnings.append(f"monthly ({monthly_percent:.0f}%)")
            
            if warnings:
                status = BudgetStatus.WARNING
                status_message = f"Approaching limit: {', '.join(warnings)}"
        
        return SpendSummary(
            daily_spend=round(daily_spend, 4),
            weekly_spend=round(weekly_spend, 4),
            monthly_spend=round(monthly_spend, 4),
            daily_remaining=round(daily_remaining, 4),
            weekly_remaining=round(weekly_remaining, 4),
            monthly_remaining=round(monthly_remaining, 4),
            daily_percent=round(daily_percent, 1),
            weekly_percent=round(weekly_percent, 1),
            monthly_percent=round(monthly_percent, 1),
            status=status,
            status_message=status_message,
        )
    
    def _get_period_spend(self, hours: int) -> float:
        """Get total spend for time period."""
        if not self.storage:
            return 0.0
        
        summary = self.storage.get_summary(period_hours=hours)
        return summary.get("estimated_cost", 0.0)
    
    def check_budget_allowed(self, estimated_cost: float = 0.0) -> tuple[bool, str]:
        """
        Check if a request should be allowed based on budget.
        
        Args:
            estimated_cost: Estimated cost of the pending request
            
        Returns:
            Tuple of (allowed, reason)
        """
        if not self.config.hard_limit:
            return True, "Budget enforcement is advisory only"
        
        summary = self.get_spend_summary()
        
        if summary.status == BudgetStatus.EXCEEDED:
            return False, summary.status_message
        
        # Check if this request would exceed any limit
        if self.config.daily_limit > 0:
            if summary.daily_spend + estimated_cost > self.config.daily_limit:
                return False, "Request would exceed daily budget limit"
        
        if self.config.weekly_limit > 0:
            if summary.weekly_spend + estimated_cost > self.config.weekly_limit:
                return False, "Request would exceed weekly budget limit"
        
        if self.config.monthly_limit > 0:
            if summary.monthly_spend + estimated_cost > self.config.monthly_limit:
                return False, "Request would exceed monthly budget limit"
        
        return True, "Within budget"
    
    def get_budget_status(self) -> dict:
        """Get complete budget status for API response."""
        summary = self.get_spend_summary()
        
        return {
            "config": self.config.to_dict(),
            "spend": summary.to_dict(),
            "enforcement": "hard" if self.config.hard_limit else "advisory",
        }


# Global default instance
default_budget_manager = BudgetManager()
