"""
Configuration and constants for the S&P Global & CRISIL AI/NLP Risk Engine
and Tactical Index Rebalancer.
"""

from typing import Dict, List, Any

# 1. The Nifty 10 Universe
# Mapping of stock tickers to their company names and entity aliases for NLP resolution
NIFTY_10_BASKET: Dict[str, Dict[str, Any]] = {
    "RELIANCE": {
        "name": "Reliance Industries Ltd",
        "sector": "Energy & Conglomerate",
        "aliases": ["reliance", "ril", "mukesh ambani", "jio", "reliance industries"]
    },
    "TCS": {
        "name": "Tata Consultancy Services Ltd",
        "sector": "IT Services",
        "aliases": ["tcs", "tata consultancy", "tata consultancy services"]
    },
    "INFY": {
        "name": "Infosys Ltd",
        "sector": "IT Services",
        "aliases": ["infosys", "infy", "salil parekh"]
    },
    "HDFCBANK": {
        "name": "HDFC Bank Ltd",
        "sector": "Banking & Financials",
        "aliases": ["hdfc bank", "hdfc", "hdfcbank"]
    },
    "ICICIBANK": {
        "name": "ICICI Bank Ltd",
        "sector": "Banking & Financials",
        "aliases": ["icici bank", "icici", "icicibank"]
    },
    "SBIN": {
        "name": "State Bank of India",
        "sector": "Public Banking",
        "aliases": ["state bank of india", "sbi", "sbin"]
    },
    "BHARTIARTL": {
        "name": "Bharti Airtel Ltd",
        "sector": "Telecommunications",
        "aliases": ["bharti airtel", "airtel", "sunil mittal", "bharti"]
    },
    "ITC": {
        "name": "ITC Ltd",
        "sector": "FMCG & Diversified",
        "aliases": ["itc", "itc limited", "itc ltd"]
    },
    "LT": {
        "name": "Larsen & Toubro Ltd",
        "sector": "Engineering & Infrastructure",
        "aliases": ["larsen & toubro", "l&t", "larsen and toubro", "lt"]
    },
    "HINDUNILVR": {
        "name": "Hindustan Unilever Ltd",
        "sector": "Consumer Goods (FMCG)",
        "aliases": ["hindustan unilever", "hul", "unilever india"]
    }
}

TICKERS: List[str] = list(NIFTY_10_BASKET.keys())
EQUAL_WEIGHT: float = 1.0 / len(TICKERS)  # 0.10 (10% each)

# 2. Portfolio Rebalancing Constraints
MIN_WEIGHT: float = 0.05       # 5% minimum floor to ensure diversification
MAX_WEIGHT: float = 0.20       # 20% maximum ceiling to prevent single-stock concentration
MAX_CYCLE_MOVEMENT: float = 0.02 # Max +/- 2.0% change per rebalance cycle
MAX_TURNOVER: float = 0.10     # Max 10% portfolio turnover per cycle
TILT_ALPHA: float = 0.5        # Exponential tilt sensitivity factor

# 3. Source Credibility Coefficients
SOURCE_WEIGHTS: Dict[str, float] = {
    "announcement": 1.0,  # Official regulatory/exchange filings
    "news": 0.8,          # Verified financial news (ET, Reuters, Bloomberg)
    "social": 0.3         # Social media (Twitter/X, Reddit) - noisier
}

# 4. Event Classification Taxonomies
EVENT_TAXONOMY: List[str] = [
    "Macroeconomic",
    "Geopolitical",
    "Credit Event",
    "M&A / Restructuring",
    "Earnings & Financials",
    "Regulatory / Legal",
    "Product / Technology",
    "Operational & Governance"
]
