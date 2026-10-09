"""Quick test script for the Data Ingestion module."""
import logging
logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")

from src.ingestion.collector import DataCollector

collector = DataCollector()

# Test 1: Fetch News
print("\n" + "=" * 50)
print("SOURCE 1: FINANCIAL NEWS")
print("=" * 50)
news = collector.fetch_news(limit=3)
for item in news:
    ticker_label = item.target_ticker or "UNRESOLVED"
    print(f"  [{ticker_label}] {item.title[:70]}")

# Test 2: Fetch Social
print("\n" + "=" * 50)
print("SOURCE 3: SOCIAL MEDIA (Reddit/Twitter)")
print("=" * 50)
social = collector.fetch_social(limit=3)
for item in social:
    ticker_label = item.target_ticker or "UNRESOLVED"
    print(f"  [{ticker_label}] {item.title[:70]}")

# Test 3: List Replay Scenarios
print("\n" + "=" * 50)
print("REPLAY SCENARIOS AVAILABLE")
print("=" * 50)
scenarios = collector.get_available_scenarios()
for key, info in scenarios.items():
    print(f"  {key}: {info['name']} ({info['item_count']} items)")

# Test 4: Load a specific scenario
print("\n" + "=" * 50)
print("LOADING SCENARIO: Tech Surge")
print("=" * 50)
tech_items = collector.load_replay_scenario("scenario_tech_surge")
for item in tech_items:
    ticker_label = item.target_ticker or "UNRESOLVED"
    print(f"  [{item.source}] [{ticker_label}] {item.title[:60]}")

print("\n--- All ingestion tests passed! ---")
