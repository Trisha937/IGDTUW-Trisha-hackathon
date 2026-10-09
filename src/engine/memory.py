"""
Local 7-Day Memory & RAG (Retrieval-Augmented Generation) Vector Engine.

This module provides:
1. Fast semantic embedding generation (via sentence-transformers with a NumPy fallback).
2. Rolling 7-day memory storage for news, announcements, and social items.
3. Cosine similarity vector search with temporal recency decay.
4. Ticker-specific evidence context formatting for LLM prompt grounding.
"""

import json
import logging
import math
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

import numpy as np

from src.ingestion.models import RawTextItem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class MemoryRecord:
    """
    Represents an item stored in the local vector memory store.
    """
    id: str
    ticker: Optional[str]
    title: str
    text: str
    source: str
    published_at: str
    embedding: List[float] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryRecord":
        """Instantiate record from dictionary."""
        return cls(**data)


@dataclass
class SearchResult:
    """
    Result container for a vector search query.
    """
    record: MemoryRecord
    similarity: float       # Raw cosine similarity [-1.0, 1.0]
    recency_weight: float   # Exponential time decay factor [0.0, 1.0]
    combined_score: float   # Combined ranking score


# ---------------------------------------------------------------------------
# Embedding Engine (Sentence-Transformers with NumPy Hashing Fallback)
# ---------------------------------------------------------------------------

class EmbeddingEngine:
    """
    Computes dense vector representations of text.
    Uses 'sentence-transformers/all-MiniLM-L6-v2' (384 dimensions) if available.
    Falls back to a deterministic 384-dim NumPy hash vectorizer if dependencies
    are not yet installed, ensuring 100% testability without downloading 500MB torch.
    """

    DIMENSION: int = 384

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        self._using_fallback = False

    def _load_model(self):
        """Lazy loader for SentenceTransformer to save startup memory."""
        if self._model is not None or self._using_fallback:
            return

        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading SentenceTransformer: {self.model_name}...")
            self._model = SentenceTransformer(self.model_name)
            logger.info("SentenceTransformer model loaded successfully.")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. Using high-speed NumPy fallback vectorizer. "
                "Run `pip install sentence-transformers` for production semantic search."
            )
            self._using_fallback = True
        except Exception as e:
            logger.warning(f"Failed to load SentenceTransformer ({e}). Using NumPy fallback.")
            self._using_fallback = True

    def embed_text(self, text: str) -> List[float]:
        """
        Generates a 384-dimensional unit vector (L2 normalized) for a single string.
        """
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Batch-embeds a list of strings into 384-dimensional unit vectors.
        """
        if not texts:
            return []

        self._load_model()

        if self._model is not None and not self._using_fallback:
            # Dense neural embeddings
            vectors = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
            return vectors.tolist()
        else:
            # Deterministic NumPy token-hashing fallback
            return [self._fallback_embed(t) for t in texts]

    def _fallback_embed(self, text: str) -> List[float]:
        """
        Deterministic, lightweight token-hashing bag-of-words vectorizer.
        Generates a 384-dimensional L2-normalized vector without external models.
        """
        vec = np.zeros(self.DIMENSION, dtype=np.float32)
        words = re.findall(r"\b\w+\b", text.lower())

        if not words:
            return vec.tolist()

        for word in words:
            # Simple hash function mapping words into dimension buckets
            h = hash(word) % self.DIMENSION
            # Sign hash to avoid collision cancellation
            sign = 1.0 if (hash(word + "_sgn") % 2 == 0) else -1.0
            vec[h] += sign

        # L2 Normalize the vector so cosine similarity equals dot product
        norm = np.linalg.norm(vec)
        if norm > 1e-6:
            vec = vec / norm

        return vec.tolist()


# ---------------------------------------------------------------------------
# 7-Day Memory Store
# ---------------------------------------------------------------------------

class MemoryStore:
    """
    Local vector memory store with rolling 7-day window retention,
    ticker filtering, and time-decayed semantic retrieval (RAG).
    """

    def __init__(
        self,
        storage_path: Optional[Union[str, Path]] = None,
        embedding_engine: Optional[EmbeddingEngine] = None,
        retention_days: int = 7,
        decay_half_life_hours: float = 48.0
    ):
        """
        Args:
            storage_path: Optional path to JSON persistence cache.
            embedding_engine: Instance of EmbeddingEngine (created if None).
            retention_days: Rolling expiry window in days (default 7).
            decay_half_life_hours: Half-life for temporal score decay in hours.
        """
        self.storage_path = Path(storage_path) if storage_path else None
        self.embedding_engine = embedding_engine or EmbeddingEngine()
        self.retention_days = retention_days
        self.decay_half_life_hours = decay_half_life_hours

        # In-memory records list
        self.records: List[MemoryRecord] = []

        if self.storage_path and self.storage_path.exists():
            self.load_from_disk()

    # -----------------------------------------------------------------------
    # Ingestion & Add
    # -----------------------------------------------------------------------

    def add(self, item: RawTextItem, ticker: Optional[str] = None) -> MemoryRecord:
        """
        Embeds and stores a single RawTextItem into memory.
        """
        resolved_ticker = ticker or item.target_ticker
        content_to_embed = f"{item.title}. {item.text}"
        vector = self.embedding_engine.embed_text(content_to_embed)

        record = MemoryRecord(
            id=item.id,
            ticker=resolved_ticker,
            title=item.title,
            text=item.text,
            source=item.source,
            published_at=item.published_at,
            embedding=vector,
            metadata={
                "url": item.url,
                "author": item.author
            }
        )
        self.records.append(record)
        return record

    def add_batch(self, items: List[RawTextItem]) -> List[MemoryRecord]:
        """
        Batch embeds and adds multiple RawTextItems efficiently.
        """
        if not items:
            return []

        # Combine titles and texts for embedding batch
        texts_to_embed = [f"{item.title}. {item.text}" for item in items]
        vectors = self.embedding_engine.embed_batch(texts_to_embed)

        new_records = []
        for item, vec in zip(items, vectors):
            record = MemoryRecord(
                id=item.id,
                ticker=item.target_ticker,
                title=item.title,
                text=item.text,
                source=item.source,
                published_at=item.published_at,
                embedding=vec,
                metadata={
                    "url": item.url,
                    "author": item.author
                }
            )
            self.records.append(record)
            new_records.append(record)

        return new_records

    # -----------------------------------------------------------------------
    # Retrieval (RAG & Cosine Search)
    # -----------------------------------------------------------------------

    def search(
        self,
        query: str,
        ticker: Optional[str] = None,
        top_k: int = 5,
        min_similarity: float = 0.05
    ) -> List[SearchResult]:
        """
        Performs semantic vector search across historical items.

        Args:
            query: Natural language query or new incoming headline.
            ticker: Optional ticker to filter by (e.g. 'INFY').
            top_k: Maximum number of results to return.
            min_similarity: Minimum cosine similarity threshold.

        Returns:
            List of SearchResult sorted by combined_score descending.
        """
        if not self.records:
            return []

        query_vector = np.array(self.embedding_engine.embed_text(query), dtype=np.float32)
        q_norm = np.linalg.norm(query_vector)
        if q_norm < 1e-6:
            return []

        # Current UTC time for temporal decay calculation
        now = datetime.now(timezone.utc)
        results: List[SearchResult] = []

        for record in self.records:
            # Ticker filter
            if ticker and record.ticker and record.ticker.upper() != ticker.upper():
                continue

            doc_vector = np.array(record.embedding, dtype=np.float32)
            d_norm = np.linalg.norm(doc_vector)
            if d_norm < 1e-6:
                continue

            # Cosine similarity: dot product of normalized vectors
            cosine_sim = float(np.dot(query_vector, doc_vector) / (q_norm * d_norm))

            if cosine_sim < min_similarity:
                continue

            # Temporal decay weight calculation:
            # recency = exp(-ln(2) * age_hours / half_life_hours)
            recency_weight = self._compute_recency_weight(record.published_at, now)
            combined_score = cosine_sim * (0.6 + 0.4 * recency_weight)

            results.append(
                SearchResult(
                    record=record,
                    similarity=cosine_sim,
                    recency_weight=recency_weight,
                    combined_score=combined_score
                )
            )

        # Sort by combined score descending
        results.sort(key=lambda x: x.combined_score, reverse=True)
        return results[:top_k]

    def _compute_recency_weight(self, published_at_str: str, now: datetime) -> float:
        """
        Computes exponential decay weight between 0.0 and 1.0 based on item age.
        """
        try:
            # Clean ISO string and parse
            clean_str = published_at_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            
            age_hours = max(0.0, (now - dt).total_seconds() / 3600.0)
            # Half-life exponential decay: e^(-lambda * t) where lambda = ln(2)/half_life
            decay_lambda = math.log(2.0) / max(1.0, self.decay_half_life_hours)
            return float(math.exp(-decay_lambda * age_hours))
        except Exception:
            return 1.0  # Fallback to no decay if date unparseable

    def get_ticker_context(self, ticker: str, top_k: int = 5) -> str:
        """
        Formats recent historical context for a specific ticker into
        a structured markdown block suitable for LLM RAG prompt injection.
        """
        matching = [r for r in self.records if r.ticker and r.ticker.upper() == ticker.upper()]
        if not matching:
            return f"No prior 7-day memory records found for {ticker}."

        # Sort matching by publication date descending (most recent first)
        matching.sort(key=lambda r: r.published_at, reverse=True)
        recent_items = matching[:top_k]

        lines = [f"### 7-Day Context for {ticker} ({len(recent_items)} recent records):"]
        for idx, item in enumerate(recent_items, 1):
            date_short = item.published_at[:10]
            lines.append(f"{idx}. [{date_short} | {item.source.upper()}] **{item.title}**: {item.text[:140]}...")

        return "\n".join(lines)

    # -----------------------------------------------------------------------
    # 7-Day Rolling Retention & Purge
    # -----------------------------------------------------------------------

    def purge_expired(self, window_days: Optional[int] = None) -> int:
        """
        Removes all records published earlier than the retention window.
        Returns the number of pruned records.
        """
        days = window_days if window_days is not None else self.retention_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        original_count = len(self.records)
        kept: List[MemoryRecord] = []

        for record in self.records:
            try:
                clean_str = record.published_at.replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

                if dt >= cutoff:
                    kept.append(record)
            except Exception:
                # If date parsing fails, keep the record to be safe
                kept.append(record)

        self.records = kept
        pruned = original_count - len(self.records)
        if pruned > 0:
            logger.info(f"Purged {pruned} records older than {days} days.")
        return pruned

    # -----------------------------------------------------------------------
    # Utilities & Persistence
    # -----------------------------------------------------------------------

    def count(self) -> int:
        """Total records currently held in memory."""
        return len(self.records)

    def clear(self):
        """Wipes all records from memory."""
        self.records.clear()

    def save_to_disk(self, filepath: Optional[Union[str, Path]] = None):
        """Serializes records and embeddings to JSON on disk."""
        target = Path(filepath) if filepath else self.storage_path
        if not target:
            raise ValueError("No filepath specified to save memory.")

        target.parent.mkdir(parents=True, exist_ok=True)
        data = [r.to_dict() for r in self.records]
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved {len(self.records)} memory records to {target}")

    def load_from_disk(self, filepath: Optional[Union[str, Path]] = None):
        """Loads records and embeddings from JSON cache on disk."""
        target = Path(filepath) if filepath else self.storage_path
        if not target or not target.exists():
            return

        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.records = [MemoryRecord.from_dict(d) for d in data]
        logger.info(f"Loaded {len(self.records)} memory records from {target}")
