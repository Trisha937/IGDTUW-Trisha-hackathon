"""
Verification and Unit Tests for Local 7-Day Memory & RAG Vector Engine.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from src.ingestion.models import RawTextItem
from src.engine.memory import MemoryStore, EmbeddingEngine

def test_memory_engine():
    print("=" * 60)
    print("Testing Embedding Engine & Local 7-Day Memory Store (RAG)")
    print("=" * 60)

    # 1. Initialize store
    cache_path = Path("data/test_memory_cache.json")
    if cache_path.exists():
        cache_path.unlink()

    store = MemoryStore(storage_path=cache_path, retention_days=7)

    # 2. Create sample news items (recent and older)
    now = datetime.now(timezone.utc)
    day2_ago = (now - timedelta(days=2)).isoformat()
    day8_ago = (now - timedelta(days=8)).isoformat() # Older than 7 days

    item1 = RawTextItem(
        title="Infosys signs $1.5B AI deal with European telco",
        text="Infosys expands global footprint with major cloud and generative AI infrastructure agreement.",
        source="news",
        target_ticker="INFY",
        published_at=now.isoformat()
    )

    item2 = RawTextItem(
        title="TCS beats revenue estimates in Q3 results",
        text="Tata Consultancy Services reports 6% YoY margin growth powered by BFSI cloud migrations.",
        source="news",
        target_ticker="TCS",
        published_at=day2_ago
    )

    item3 = RawTextItem(
        title="Infosys CEO Salil Parekh announces strategic hiring freeze",
        text="Infosys management pauses fresh campus intake to focus on internal automation and re-skilling.",
        source="social",
        target_ticker="INFY",
        published_at=day8_ago # Will expire upon 7-day purge
    )

    item4 = RawTextItem(
        title="Reliance Jio launches satellite broadband network",
        text="Reliance Jio partners with SES to provide low-latency satellite internet across rural India.",
        source="announcement",
        target_ticker="RELIANCE",
        published_at=now.isoformat()
    )

    # 3. Add to memory store
    print("\n[Step 1] Adding items to MemoryStore...")
    records = store.add_batch([item1, item2, item3, item4])
    print(f"-> Added {len(records)} records. Total memory count: {store.count()}")
    assert store.count() == 4, f"Expected 4 items, got {store.count()}"

    # 4. Search RAG for INFY AI news
    print("\n[Step 2] Performing semantic vector search (RAG retrieval)...")
    query = "Infosys artificial intelligence deal"
    results = store.search(query=query, ticker="INFY", top_k=3)

    print(f"Query: '{query}' (Ticker Filter: INFY)")
    for i, res in enumerate(results, 1):
        print(f"  {i}. Score: {res.combined_score:.4f} (Sim: {res.similarity:.4f}, Recency: {res.recency_weight:.4f})")
        print(f"     Title: {res.record.title} | Published: {res.record.published_at[:10]}")

    assert len(results) > 0, "Expected search results"
    assert results[0].record.ticker == "INFY"
    # item1 should rank first due to higher similarity and zero age decay
    assert "deal" in results[0].record.title.lower() or "ai" in results[0].record.title.lower()

    # 5. Format prompt context for LLM RAG injection
    print("\n[Step 3] Generating LLM Prompt Context block...")
    context_str = store.get_ticker_context("INFY")
    print(context_str)
    assert "INFY" in context_str

    # 6. Test 7-Day Purge
    print("\n[Step 4] Testing 7-day retention purge...")
    pruned = store.purge_expired(window_days=7)
    print(f"-> Pruned {pruned} expired record(s). Remaining: {store.count()}")
    assert pruned == 1, f"Expected 1 record (day 8 item) pruned, got {pruned}"
    assert store.count() == 3, f"Expected 3 records remaining, got {store.count()}"

    # 7. Test Persistence (Save and Reload)
    print("\n[Step 5] Testing disk persistence...")
    store.save_to_disk()
    assert cache_path.exists(), "Cache file was not saved!"

    new_store = MemoryStore(storage_path=cache_path)
    print(f"-> Reloaded new store from disk. Total count: {new_store.count()}")
    assert new_store.count() == 3, f"Expected 3 records reloaded, got {new_store.count()}"

    # Clean up test artifact
    if cache_path.exists():
        cache_path.unlink()

    print("\n" + "=" * 60)
    print("ALL 5 MEMORY & RAG TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    test_memory_engine()
