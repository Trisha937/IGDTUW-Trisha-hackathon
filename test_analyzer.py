"""
Verification and Test script for AI/NLP Risk Engine (analyzer.py).
"""

from src.ingestion.models import RawTextItem
from src.engine.analyzer import RiskAnalyzer
from src.engine.memory import MemoryStore

def test_risk_analyzer():
    print("=" * 65)
    print("TESTING AI/NLP RISK ENGINE & ENTITY RESOLUTION")
    print("=" * 65)

    analyzer = RiskAnalyzer()
    memory = MemoryStore()

    # Test cases representing diverse events & sources
    test_items = [
        RawTextItem(
            title="RBI imposes Rs 10 crore penalty on HDFC Bank over compliance lapses",
            text="The Reserve Bank of India issued an order citing irregularities in lending guidelines.",
            source="news"
        ),
        RawTextItem(
            title="Infosys signs record $1.5B multi-year cloud contract with European partner",
            text="Infosys expects this deal to boost digital service revenues and operating margins.",
            source="announcement"
        ),
        RawTextItem(
            title="TCS beats street estimates with 8% profit growth in Q3 results",
            text="Tata Consultancy Services reports solid margin expansion led by UK and US banking clients.",
            source="news"
        ),
        RawTextItem(
            title="Mukesh Ambani announces major 5G expansion and green energy partnership",
            text="Reliance industries accelerates capital expenditure for nationwide network rollout.",
            source="news"
        ),
        RawTextItem(
            title="Rumors on Reddit that ICICI Bank executive resigned over internal probe",
            text="Social media chatter claims key banking officer stepped down amidst audit review.",
            source="social"
        )
    ]

    # Populate memory first
    memory.add_batch(test_items)

    print("\nRunning Batch Risk Analysis...")
    batch = analyzer.analyze_batch(test_items, memory_store=memory)

    print(f"\nAnalyzed: {batch.total_items_analyzed} items")
    print(f"Generated Signals: {len(batch.signals)}")
    print(f"Unresolved Count: {batch.unresolved_count}\n")

    for i, sig in enumerate(batch.signals, 1):
        print(f"[{i}] Ticker: {sig.ticker:<10} | Source: {sig.source:<12}")
        print(f"    Sentiment: {sig.sentiment_score:+.3f} | Event: {sig.event_classification}")
        print(f"    Impact: {sig.impact_score}/10       | Conf: {sig.confidence:.2f}")
        print(f"    Reason: {sig.reason}\n")

    # Assertions
    assert len(batch.signals) == 5, f"Expected 5 signals, got {len(batch.signals)}"
    
    # 1. HDFC Bank should be negative, Regulatory/Legal
    hdfc_sig = next(s for s in batch.signals if s.ticker == "HDFCBANK")
    assert hdfc_sig.sentiment_score < 0, "HDFCBANK penalty should be negative sentiment"
    assert hdfc_sig.event_classification == "Regulatory / Legal"

    # 2. Infosys should be positive, Announcement
    infy_sig = next(s for s in batch.signals if s.ticker == "INFY")
    assert infy_sig.sentiment_score > 0, "INFY contract should be positive sentiment"

    # 3. TCS should be positive, Earnings & Financials
    tcs_sig = next(s for s in batch.signals if s.ticker == "TCS")
    assert tcs_sig.sentiment_score > 0, "TCS profit beat should be positive sentiment"
    assert tcs_sig.event_classification == "Earnings & Financials"

    # 4. Reliance resolved from 'Mukesh Ambani' alias
    ril_sig = next(s for s in batch.signals if s.ticker == "RELIANCE")
    assert ril_sig.ticker == "RELIANCE", "Failed to resolve Mukesh Ambani to RELIANCE"

    # 5. ICICI Social post should have lower source credibility / confidence
    icici_sig = next(s for s in batch.signals if s.ticker == "ICICIBANK")
    assert icici_sig.source == "social"
    assert icici_sig.confidence < 0.8, "Social media post should have lower confidence than news"

    print("=" * 65)
    print("ALL AI/NLP RISK ENGINE TESTS PASSED SUCCESSFULLY!")
    print("=" * 65)

if __name__ == "__main__":
    test_risk_analyzer()
