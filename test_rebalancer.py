"""
Comprehensive Unit Tests for Tactical Stock Index Rebalancer (optimizer.py).
"""

from src.engine.models import RiskSignal
from src.rebalancer.optimizer import IndexRebalancer
from src.config import TICKERS

def test_index_rebalancer():
    print("=" * 65)
    print("TESTING MODULE A: TACTICAL STOCK INDEX REBALANCER")
    print("=" * 65)

    rebalancer = IndexRebalancer()

    # 1. Baseline State (Cycle 0)
    print("\n[Step 1] Verifying Baseline Portfolio (Cycle 0)...")
    init_state = rebalancer.get_current_portfolio()
    print(f"Cycle: {init_state.cycle_number} | Total Weight: {init_state.total_weight:.4f}")
    assert init_state.cycle_number == 0
    assert abs(init_state.total_weight - 1.0) < 1e-4

    for t in TICKERS:
        alloc = init_state.allocations[t]
        assert alloc.weight == 0.10, f"Expected 0.10 for {t}, got {alloc.weight}"
        assert alloc.weight_pct == 10.0
    print("-> Baseline verified: Exactly 10.0% allocated across all 10 stocks.")

    # 2. Cycle 1: Strong Positive Signal on INFY, Strong Negative Signal on HDFCBANK
    print("\n[Step 2] Executing Rebalance Cycle 1 (Infosys surge, HDFC penalty)...")
    sig1 = RiskSignal(
        ticker="INFY",
        sentiment_score=0.85,
        event_classification="Earnings & Financials",
        impact_score=8,
        confidence=0.92,
        reason="Infosys signs record $1.5B cloud deal",
        source="announcement"
    )
    sig2 = RiskSignal(
        ticker="HDFCBANK",
        sentiment_score=-0.80,
        event_classification="Regulatory / Legal",
        impact_score=9,
        confidence=0.85,
        reason="RBI regulatory fine on compliance lapse",
        source="news"
    )

    state_c1 = rebalancer.rebalance([sig1, sig2], reason="Test Cycle 1: INFY bull, HDFC bear")

    print(f"Cycle #{state_c1.cycle_number} | Turnover: {state_c1.turnover * 100:.2f}%")
    print("Weights after Cycle 1:")
    for t in TICKERS:
        alloc = state_c1.allocations[t]
        delta_str = f"({alloc.delta_weight * 100:+.2f}%)" if alloc.delta_weight != 0 else "( 0.00%)"
        print(f"  {t:<10}: {alloc.weight_pct:5.2f}% {delta_str} | Sent: {alloc.sentiment_score:+.2f}")

    # Check assertions for Cycle 1:
    assert state_c1.cycle_number == 1
    assert abs(state_c1.total_weight - 1.0) < 1e-3, f"Sum must be 1.0, got {state_c1.total_weight}"
    # INFY should increase, but clamped by MAX_CYCLE_MOVEMENT (<= 12.0%)
    infy_w = state_c1.allocations["INFY"].weight
    assert infy_w > 0.10, "INFY weight should increase"
    assert infy_w <= 0.12001, f"INFY weight cannot increase by more than 2.0% in one cycle (got {infy_w})"

    # HDFCBANK should decrease, but clamped by MAX_CYCLE_MOVEMENT (>= 8.0%)
    hdfc_w = state_c1.allocations["HDFCBANK"].weight
    assert hdfc_w < 0.10, "HDFCBANK weight should decrease"
    assert hdfc_w >= 0.07999, f"HDFCBANK weight cannot drop by more than 2.0% in one cycle (got {hdfc_w})"

    # 3. Cycle 2: Compounded Move (Another strong INFY quarter)
    print("\n[Step 3] Executing Rebalance Cycle 2 (Compounding INFY growth)...")
    sig3 = RiskSignal(
        ticker="INFY",
        sentiment_score=0.90,
        event_classification="Earnings & Financials",
        impact_score=8,
        confidence=0.95,
        reason="Infosys raises FY revenue guidance",
        source="announcement"
    )
    state_c2 = rebalancer.rebalance([sig3], reason="Test Cycle 2: INFY guidance raise")

    infy_w2 = state_c2.allocations["INFY"].weight
    print(f"INFY after Cycle 2: {state_c2.allocations['INFY'].weight_pct:.2f}% (Total Delta from baseline: {(infy_w2 - 0.10)*100:+.2f}%)")
    assert infy_w2 > infy_w, "INFY weight should grow further in Cycle 2"
    assert infy_w2 <= 0.14001, "INFY cannot exceed 14% after 2 cycles of 2% max steps"

    # 4. Check Hard Bounds Constraint
    print("\n[Step 4] Verifying all portfolio constraints...")
    for t in TICKERS:
        w = state_c2.allocations[t].weight
        assert 0.05 <= w <= 0.20, f"Stock {t} weight {w} violated [5%, 20%] bound!"
    print("-> All 10 stocks strictly adhere to [5.0%, 20.0%] bounds.")

    # 5. Check History Audit Log
    history = rebalancer.get_history()
    print(f"\n[Step 5] Checking Rebalance History Audit Trail...")
    print(f"Total historical states recorded: {len(history)}")
    assert len(history) == 3, f"Expected 3 states (Cycle 0, 1, 2), got {len(history)}"

    print("\n" + "=" * 65)
    print("ALL MODULE A REBALANCER TESTS PASSED SUCCESSFULLY!")
    print("=" * 65)

if __name__ == "__main__":
    test_index_rebalancer()
