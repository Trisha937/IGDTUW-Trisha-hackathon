"""
Data models for the Tactical Stock Index Rebalancer.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

class StockAllocation(BaseModel):
    """Allocation details for an individual stock in the basket."""
    ticker: str
    name: str
    sector: str
    weight: float = Field(..., ge=0.0, le=1.0, description="Portfolio allocation weight [0.0 to 1.0]")
    weight_pct: float = Field(..., description="Weight displayed as a percentage (e.g. 10.0 for 10%)")
    sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    target_weight_raw: float = Field(default=0.10)
    delta_weight: float = Field(default=0.0, description="Change from previous rebalance cycle")

class PortfolioState(BaseModel):
    """Snapshot of portfolio weights at a specific point in time."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    allocations: Dict[str, StockAllocation]
    total_weight: float = Field(default=1.0)
    turnover: float = Field(default=0.0, description="One-way portfolio turnover in this cycle")
    cycle_number: int = Field(default=0)
    rebalance_reason: str = Field(default="Initial portfolio state (Equal-weight)")
    active_signals_count: int = Field(default=0)
    signals_applied: List[str] = Field(default_factory=list, description="IDs of applied RiskSignals")

class RebalanceHistory(BaseModel):
    """Historical audit log of rebalancing cycles."""
    states: List[PortfolioState] = Field(default_factory=list)
