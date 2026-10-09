"""
API and End-to-End System Tests for Module A Web Application.
"""

from fastapi.testclient import TestClient
from src.api.main import app

def test_api_endpoints():
    print("=" * 65)
    print("TESTING FASTAPI BACKEND & END-TO-END PIPELINE (MODULE A)")
    print("=" * 65)

    client = TestClient(app)

    # 1. Health check
    print("\n[Test 1] GET /health...")
    resp = client.get("/health")
    assert resp.status_code == 200, f"Health check failed: {resp.text}"
    data = resp.json()
    print("-> Health Status:", data)
    assert data["status"] == "healthy"
    assert data["nifty_constituents"] == 10

    # 2. Portfolio baseline
    print("\n[Test 2] GET /api/portfolio (Baseline)...")
    resp = client.get("/api/portfolio")
    assert resp.status_code == 200
    portfolio = resp.json()
    assert portfolio["cycle_number"] == 0
    assert abs(portfolio["total_weight"] - 1.0) < 1e-4
    print(f"-> Cycle: {portfolio['cycle_number']} | Constituents: {len(portfolio['allocations'])}")

    # 3. Trigger Replay Scenario A (Tech Surge)
    print("\n[Test 3] POST /api/replay/scenario_tech_surge...")
    resp = client.post("/api/replay/scenario_tech_surge")
    assert resp.status_code == 200, f"Replay failed: {resp.text}"
    replay_data = resp.json()
    print(f"-> Ingested: {replay_data['items_ingested']} items | Signals: {replay_data['signals_extracted']}")
    print(f"-> New Cycle: {replay_data['portfolio']['cycle_number']}")
    assert replay_data["portfolio"]["cycle_number"] == 1
    # Check that INFY weight tilted up
    infy_alloc = replay_data["portfolio"]["allocations"]["INFY"]
    print(f"-> INFY Weight: {infy_alloc['weight_pct']:.2f}% (Delta: {infy_alloc['delta_weight']*100:+.2f}%)")
    assert infy_alloc["weight"] > 0.10

    # 4. Check Signals Feed
    print("\n[Test 4] GET /api/signals...")
    resp = client.get("/api/signals")
    assert resp.status_code == 200
    signals = resp.json()
    print(f"-> Active signals in feed: {len(signals)}")
    assert len(signals) >= 2

    # 5. Ingest Custom Article
    print("\n[Test 5] POST /api/analyze-custom (SEBI probe on Reliance)...")
    custom_payload = {
        "title": "SEBI issues query to Reliance Industries regarding subsidiary disclosures",
        "text": "Market regulator seeks clarifications on foreign institutional investment flows into retail units.",
        "source": "news",
        "target_ticker": "RELIANCE"
    }
    resp = client.post("/api/analyze-custom", json=custom_payload)
    assert resp.status_code == 200
    custom_res = resp.json()
    print("-> Custom Ingestion Result:", custom_res["success"])
    assert custom_res["success"] is True
    assert custom_res["signal"]["ticker"] == "RELIANCE"

    # 6. Reset Portfolio
    print("\n[Test 6] POST /api/reset...")
    resp = client.post("/api/reset")
    assert resp.status_code == 200
    reset_data = resp.json()
    print("-> Reset Status:", reset_data["message"])
    assert reset_data["portfolio"]["cycle_number"] == 0

    # 7. Check Frontend Static Serving
    print("\n[Test 7] GET / (Dashboard HTML)...")
    resp = client.get("/")
    assert resp.status_code == 200
    assert "S&P Global" in resp.text
    assert "Nifty 10" in resp.text
    print("-> Dashboard index.html successfully served!")

    print("\n" + "=" * 65)
    print("ALL API & FULL PIPELINE TESTS PASSED!")
    print("=" * 65)

if __name__ == "__main__":
    test_api_endpoints()
