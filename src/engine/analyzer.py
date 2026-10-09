"""
AI/NLP Risk Engine for Financial Signal Extraction.

Performs:
1. Entity Resolution (Mapping textual mentions/aliases to Nifty 10 tickers).
2. Multi-Source Sentiment Scoring (-1.0 to +1.0).
3. Event Classification into Financial Taxonomy.
4. Impact Severity Scoring (1 to 10 scale).
5. Grounded Explanation with Source Evidence References.
6. Dual Execution Mode: NVIDIA Nemotron LLM inference with an instant,
   zero-dependency Financial Lexicon fallback.
"""

import json
import logging
import os
import re
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from src.config import NIFTY_10_BASKET, EVENT_TAXONOMY, SOURCE_WEIGHTS
from src.ingestion.models import RawTextItem
from src.engine.models import RiskSignal, AnalysisBatch
from src.engine.memory import MemoryStore

load_dotenv()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Financial Lexicon & Heuristics (Deterministic Fallback)
# ---------------------------------------------------------------------------

BULLISH_KEYWORDS = {
    "surge": 0.6, "soar": 0.7, "profit": 0.5, "beats": 0.7, "record": 0.6,
    "growth": 0.4, "dividend": 0.5, "win": 0.5, "wins": 0.5, "deal": 0.4,
    "upgraded": 0.8, "robust": 0.5, "expansion": 0.5, "rally": 0.6,
    "buyback": 0.6, "outperform": 0.7, "bullish": 0.6, "innovative": 0.4,
    "high": 0.3, "gains": 0.5, "partnership": 0.4, "contract": 0.5,
    "approved": 0.5, "exceeds": 0.6, "strong": 0.4, "breakthrough": 0.7
}

BEARISH_KEYWORDS = {
    "crash": -0.8, "drop": -0.4, "slump": -0.6, "loss": -0.6, "probe": -0.7,
    "penalty": -0.7, "fine": -0.6, "investigation": -0.7, "resigned": -0.5,
    "downgrade": -0.8, "lawsuit": -0.6, "fraud": -0.9, "default": -0.9,
    "debt": -0.4, "crisis": -0.8, "fell": -0.4, "missed": -0.6,
    "decline": -0.4, "plunge": -0.7, "scam": -0.9, "irregularities": -0.8,
    "sanction": -0.7, "strike": -0.5, "layoffs": -0.5, "weak": -0.4,
    "freeze": -0.4, "violation": -0.7, "warning": -0.5, "litigation": -0.6
}

TAXONOMY_KEYWORDS = {
    "Regulatory / Legal": ["sebi", "rbi", "penalty", "fine", "court", "probe", "investigation", "lawsuit", "tax", "notice", "ed", "compliance", "violation"],
    "Earnings & Financials": ["q1", "q2", "q3", "q4", "quarter", "profit", "revenue", "ebitda", "dividend", "loss", "margin", "earnings", "pat", "results"],
    "M&A / Restructuring": ["merger", "acquisition", "acquire", "stake", "buyout", "demerger", "amalgamation", "takeover", "restructuring", "divestment"],
    "Operational & Governance": ["ceo", "cfo", "resigned", "board", "promoter", "misconduct", "irregularities", "hiring freeze", "auditor", "governance"],
    "Product / Technology": ["launch", "ai", "platform", "cloud", "5g", "patent", "digital", "data center", "technology", "software", "solution"],
    "Credit Event": ["default", "downgrade", "npa", "credit rating", "insolvency", "nclt", "debt default", "liquidity crunch", "bond yield"],
    "Macroeconomic": ["inflation", "gdp", "interest rate", "repo rate", "crude", "fiscal", "budget", "rbi policy", "rupee", "forex"],
    "Geopolitical": ["tariff", "war", "sanction", "export ban", "trade war", "conflict", "customs duty"]
}


# ---------------------------------------------------------------------------
# Core Risk Engine Analyzer
# ---------------------------------------------------------------------------

class RiskAnalyzer:
    """
    Analyzes raw textual items to extract structured risk signals.
    """

    def __init__(
        self,
        nvidia_api_key: Optional[str] = None,
        model_name: str = "nvidia/nemotron-3.5-lightning-30b-a3b",
        api_base_url: str = "https://integrate.api.nvidia.com/v1"
    ):
        self.api_key = nvidia_api_key or os.getenv("NVIDIA_API_KEY")
        self.model_name = model_name
        self.api_base_url = api_base_url
        self.use_llm = bool(self.api_key and self.api_key.strip() and self.api_key != "your_nvidia_api_key_here")

        if self.use_llm:
            logger.info(f"RiskAnalyzer initialized with NVIDIA LLM: {self.model_name}")
        else:
            logger.info("NVIDIA_API_KEY not configured. RiskAnalyzer running with Financial Lexicon engine.")

    # -----------------------------------------------------------------------
    # Entity Resolution (Text -> Nifty 10 Ticker)
    # -----------------------------------------------------------------------

    def resolve_ticker(self, text: str, title: str) -> Optional[str]:
        """
        Scans title and text against Nifty 10 aliases to resolve company ticker.
        Title matches receive highest priority.
        """
        combined = f"{title} {text}".lower()

        # Check each company in the basket
        best_match = None
        best_len = 0

        for ticker, info in NIFTY_10_BASKET.items():
            # Check ticker symbol directly as a distinct word
            if re.search(rf"\b{ticker.lower()}\b", combined):
                return ticker

            # Check entity aliases
            for alias in info.get("aliases", []):
                pattern = rf"\b{re.escape(alias.lower())}\b"
                if re.search(pattern, combined):
                    # Prefer longer alias matches (e.g. 'hdfc bank' over 'hdfc')
                    if len(alias) > best_len:
                        best_match = ticker
                        best_len = len(alias)

        return best_match

    # -----------------------------------------------------------------------
    # Single Item Analysis
    # -----------------------------------------------------------------------

    def analyze_item(
        self,
        item: RawTextItem,
        memory_store: Optional[MemoryStore] = None
    ) -> Optional[RiskSignal]:
        """
        Extracts structured risk signal from a single RawTextItem.
        Returns None if company ticker cannot be resolved.
        """
        # 1. Resolve Target Company
        ticker = item.target_ticker or self.resolve_ticker(item.text, item.title)
        if not ticker or ticker not in NIFTY_10_BASKET:
            logger.debug(f"Could not resolve Nifty 10 ticker for item: '{item.title[:40]}'")
            return None

        # 2. Retrieve Historical Evidence Context (RAG)
        context_evidence = ""
        if memory_store:
            # Query memory store for related records
            similar_records = memory_store.search(
                query=item.title,
                ticker=ticker,
                top_k=2,
                min_similarity=0.1
            )
            if similar_records:
                context_evidence = "\n".join(
                    [f"- Past reference: {r.record.title} ({r.record.published_at[:10]})" for r in similar_records]
                )

        # 3. Perform Analysis (LLM or Heuristic)
        if self.use_llm:
            try:
                signal = self._llm_analyze(item, ticker, context_evidence)
                if signal:
                    return signal
            except Exception as e:
                logger.warning(f"LLM analysis failed ({e}). Falling back to Financial Lexicon engine.")

        # Fallback to deterministic heuristic analyzer
        return self._heuristic_analyze(item, ticker, context_evidence)

    # -----------------------------------------------------------------------
    # Batch Analysis
    # -----------------------------------------------------------------------

    def analyze_batch(
        self,
        items: List[RawTextItem],
        memory_store: Optional[MemoryStore] = None
    ) -> AnalysisBatch:
        """
        Analyzes a batch of items and packages them into an AnalysisBatch.
        """
        signals: List[RiskSignal] = []
        unresolved = 0

        for item in items:
            sig = self.analyze_item(item, memory_store=memory_store)
            if sig:
                signals.append(sig)
            else:
                unresolved += 1

        return AnalysisBatch(
            signals=signals,
            total_items_analyzed=len(items),
            unresolved_count=unresolved
        )

    # -----------------------------------------------------------------------
    # LLM Inference (NVIDIA API)
    # -----------------------------------------------------------------------

    def _llm_analyze(
        self,
        item: RawTextItem,
        ticker: str,
        context_evidence: str
    ) -> Optional[RiskSignal]:
        """
        Calls NVIDIA hosted Nemotron/Llama endpoint with structured JSON output instructions.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        system_prompt = (
            "You are an expert quantitative risk analyst for S&P Global and CRISIL.\n"
            "Analyze the given financial text regarding the company and output STRICT JSON only.\n"
            "Your output must adhere to this exact schema:\n"
            "{\n"
            '  "sentiment_score": float between -1.0 (extremely bearish) and +1.0 (extremely bullish),\n'
            f'  "event_classification": one of {json.dumps(EVENT_TAXONOMY)},\n'
            '  "impact_score": integer 1 to 10 (1-3 minor, 4-6 material company event, 7-8 major disruption, 9-10 systemic),\n'
            '  "confidence": float 0.0 to 1.0,\n'
            '  "reason": concise 1-2 sentence evidence-grounded summary\n'
            "}"
        )

        user_content = (
            f"Company Ticker: {ticker}\n"
            f"Source Stream: {item.source.upper()}\n"
            f"Headline: {item.title}\n"
            f"Content: {item.text}\n"
        )
        if context_evidence:
            user_content += f"\nRelevant Historical Context:\n{context_evidence}\n"

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.1,
            "max_tokens": 300
        }

        resp = requests.post(
            f"{self.api_base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=12.0
        )
        resp.raise_for_status()

        data = resp.json()
        raw_text = data["choices"][0]["message"]["content"]

        # Parse JSON from model output (handling possible markdown backticks)
        clean_json = re.sub(r"^```json\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE)
        parsed = json.loads(clean_json)

        return RiskSignal(
            ticker=ticker,
            sentiment_score=float(max(-1.0, min(1.0, parsed["sentiment_score"]))),
            event_classification=str(parsed.get("event_classification", "Earnings & Financials")),
            impact_score=int(max(1, min(10, parsed.get("impact_score", 5)))),
            confidence=float(max(0.0, min(1.0, parsed.get("confidence", 0.85)))),
            reason=str(parsed.get("reason", item.title)),
            evidence_ids=[item.id],
            source=item.source,
            model_version=self.model_name
        )

    # -----------------------------------------------------------------------
    # Deterministic Financial Lexicon Fallback
    # -----------------------------------------------------------------------

    def _heuristic_analyze(
        self,
        item: RawTextItem,
        ticker: str,
        context_evidence: str
    ) -> RiskSignal:
        """
        Deterministic, transparent NLP engine using financial keyword polarity,
        taxonomy regex mapping, and source credibility weighting.
        """
        combined = f"{item.title} {item.text}".lower()

        # 1. Compute Sentiment Score
        sentiment = 0.0
        keyword_hits = 0

        for word, weight in BULLISH_KEYWORDS.items():
            if re.search(rf"\b{word}\b", combined):
                sentiment += weight
                keyword_hits += 1

        for word, weight in BEARISH_KEYWORDS.items():
            if re.search(rf"\b{word}\b", combined):
                sentiment += weight
                keyword_hits += 1

        if keyword_hits > 0:
            # Average polarity clamped to [-1.0, 1.0]
            sentiment_score = max(-1.0, min(1.0, sentiment / (keyword_hits ** 0.5)))
        else:
            sentiment_score = 0.0

        # Adjust by source weight (Social media is noisier -> compress towards neutral)
        src_weight = SOURCE_WEIGHTS.get(item.source, 0.5)
        adjusted_sentiment = round(sentiment_score * src_weight, 3)

        # 2. Event Classification
        classified_event = "Earnings & Financials"  # Default
        max_matches = 0

        for event_name, keywords in TAXONOMY_KEYWORDS.items():
            matches = sum(1 for kw in keywords if re.search(rf"\b{re.escape(kw)}\b", combined))
            if matches > max_matches:
                max_matches = matches
                classified_event = event_name

        # 3. Impact Severity Scoring (1-10 Rubric)
        # Base impact from source: Announcement (6), News (5), Social (3)
        base_impact = 6 if item.source == "announcement" else (5 if item.source == "news" else 3)

        # Event type severity adjustment
        if classified_event in ["Regulatory / Legal", "Credit Event"]:
            base_impact += 2
        elif classified_event in ["M&A / Restructuring", "Geopolitical"]:
            base_impact += 1

        # Strong sentiment extremity increases impact
        if abs(adjusted_sentiment) >= 0.5:
            base_impact += 2
        elif abs(adjusted_sentiment) >= 0.2:
            base_impact += 1

        impact_score = max(1, min(10, base_impact))

        # 4. Confidence Score
        confidence = 0.92 if item.source == "announcement" else (0.85 if item.source == "news" else 0.65)

        # 5. Formulate Grounded Reason
        direction = "positive" if adjusted_sentiment > 0 else ("negative" if adjusted_sentiment < 0 else "neutral")
        reason = f"Detected {direction} {classified_event.lower()} signal for {ticker} from {item.source.upper()}: '{item.title[:90]}'"

        return RiskSignal(
            ticker=ticker,
            sentiment_score=adjusted_sentiment,
            event_classification=classified_event,
            impact_score=impact_score,
            confidence=confidence,
            reason=reason,
            evidence_ids=[item.id],
            source=item.source,
            model_version="lexicon-heuristic-v1"
        )
