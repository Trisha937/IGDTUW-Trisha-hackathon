"""
FastAPI Application & REST Endpoints for Module A: Tactical Stock Index Rebalancer.
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.config import NIFTY_10_BASKET, TICKERS, EVENT_TAXONOMY
from src.ingestion.collector import DataCollector
from src.ingestion.models import RawTextItem
from src.engine.memory import MemoryStore
from src.engine.analyzer import RiskAnalyzer
from src.engine.models import RiskSignal, AnalysisBatch
from src.rebalancer.optimizer import IndexRebalancer
from src.rebalancer.models import PortfolioState

logger = logging.getLogger("api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# ---------------------------------------------------------------------------
# Application Initialization & In-Memory Pipeline Instances
# ---------------------------------------------------------------------------

app = FastAPI(
    title="S&P Global & CRISIL Tactical Stock Index Rebalancer",
    description="Real-Time NLP Risk Engine and Dynamic Nifty 10 Portfolio Rebalancing API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core pipeline instances
collector = DataCollector()
memory = MemoryStore(retention_days=7)
analyzer = RiskAnalyzer()
rebalancer = IndexRebalancer()

# Audit log of all ingested signals in memory
active_signals_feed: List[RiskSignal] = []

# Frontend directory path (serves high-performance financial dashboard)
STATIC_DIR = Path(__file__).resolve().parent / "static"
if not STATIC_DIR.exists():
    STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class CustomArticleInput(BaseModel):
    title: str = Field(..., min_length=3, description="Headline or post title")
    text: str = Field(..., min_length=5, description="Full article or post text")
    source: str = Field(default="news", description="'news', 'announcement', or 'social'")
    target_ticker: Optional[str] = Field(default=None, description="Optional override ticker symbol")


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check():
    """Health and engine status."""
    return {
        "status": "healthy",
        "service": "Tactical Index Rebalancer (Module A)",
        "memory_records": memory.count(),
        "active_signals": len(active_signals_feed),
        "portfolio_cycle": rebalancer.get_current_portfolio().cycle_number,
        "nifty_constituents": len(TICKERS)
    }

@app.get("/api/portfolio", response_model=PortfolioState)
def get_current_portfolio():
    """Returns the current portfolio allocations and cycle state."""
    return rebalancer.get_current_portfolio()

@app.get("/api/history")
def get_portfolio_history():
    """Returns the chronological audit trail of rebalancing cycles."""
    return [state.model_dump() for state in rebalancer.get_history()]

@app.get("/api/signals")
def get_recent_signals(limit: int = 20):
    """Returns the most recent risk signals extracted by the NLP engine."""
    return [sig.model_dump() for sig in active_signals_feed[-limit:][::-1]]

@app.get("/api/scenarios")
def get_available_scenarios():
    """Returns metadata for pre-verified replay demonstration scenarios."""
    return collector.get_available_scenarios()

@app.post("/api/replay/{scenario_id}")
def run_replay_scenario(scenario_id: str):
    """
    Executes a curated market scenario:
    1. Loads items from data/replay_scenarios.json
    2. Stores in 7-day memory
    3. NLP engine extracts risk signals
    4. Rebalancer recalculates Nifty 10 weights
    """
    scenarios = collector.get_available_scenarios()
    if scenario_id not in scenarios:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found.")

    scenario_meta = scenarios[scenario_id]
    items = collector.load_replay_scenario(scenario_id)
    if not items:
        raise HTTPException(status_code=400, detail="Scenario contained no items.")

    # 1. Ingest into 7-day memory
    memory.add_batch(items)

    # 2. Analyze with AI/NLP Risk Engine
    batch = analyzer.analyze_batch(items, memory_store=memory)
    if not batch.signals:
        raise HTTPException(status_code=400, detail="No actionable company risk signals extracted.")

    # Record signals in active feed
    active_signals_feed.extend(batch.signals)

    # 3. Rebalance Portfolio
    reason = f"Replay: {scenario_meta['name']}"
    new_state = rebalancer.rebalance(batch.signals, reason=reason)

    return {
        "scenario": scenario_meta,
        "items_ingested": len(items),
        "signals_extracted": len(batch.signals),
        "signals": [s.model_dump() for s in batch.signals],
        "portfolio": new_state.model_dump()
    }

@app.post("/api/analyze-custom")
def analyze_custom_input(input_data: CustomArticleInput):
    """
    Processes user-submitted or jury-submitted news headlines in real time,
    extracts risk signals, and triggers a live portfolio rebalance.
    """
    item = RawTextItem(
        title=input_data.title,
        text=input_data.text,
        source=input_data.source,
        target_ticker=input_data.target_ticker
    )

    # Store in memory
    memory.add(item)

    # Analyze
    signal = analyzer.analyze_item(item, memory_store=memory)
    if not signal:
        return {
            "success": False,
            "message": "Item could not be resolved to any of the Nifty 10 companies.",
            "supported_tickers": TICKERS
        }

    active_signals_feed.append(signal)

    # Rebalance
    new_state = rebalancer.rebalance(
        [signal],
        reason=f"Custom Signal: {signal.ticker} ({signal.event_classification}) [{input_data.source.upper()}]"
    )

    return {
        "success": True,
        "signal": signal.model_dump(),
        "portfolio": new_state.model_dump()
    }

@app.post("/api/reset")
def reset_portfolio():
    """Resets the portfolio state back to baseline equal weights (Cycle 0)."""
    new_state = rebalancer.reset()
    active_signals_feed.clear()
    memory.clear()
    return {
        "message": "Portfolio reset to 10% equal-weight benchmark across all constituents.",
        "portfolio": new_state.model_dump()
    }

@app.get("/api/basket")
def get_nifty_basket():
    """Returns the metadata and constituent info for the Nifty 10 basket."""
    return {
        "basket": NIFTY_10_BASKET,
        "taxonomies": EVENT_TAXONOMY,
        "tickers": TICKERS
    }


# ---------------------------------------------------------------------------
# Static Frontend Serving (if built)
# ---------------------------------------------------------------------------

if STATIC_DIR.exists():
    assets_path = STATIC_DIR / "assets"
    if assets_path.exists():
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

    @app.get("/")
    async def serve_index():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "S&P Global & CRISIL Tactical Rebalancer API Active. Frontend not yet compiled."}

    @app.get("/{full_path:path}")
    async def serve_static(full_path: str):
        # 1. Check in static directory
        file_path = STATIC_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        # 2. Check in project root directory (e.g. docs/architecture.png)
        root_dir = Path(__file__).resolve().parent.parent.parent
        root_file = root_dir / full_path
        if root_file.exists() and root_file.is_file():
            return FileResponse(root_file)

        # 3. Fallback to index.html for SPA routing
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"error": "Not Found"}
