"""
Tactical Stock Index Rebalancer for the Nifty 10 Basket (Module A).

Implements:
1. Multi-source sentiment aggregation with social media noise dampening.
2. Exponential tilting allocation formula: Target ∝ 0.10 * exp(alpha * S).
3. Hard financial bounds enforcement:
   - Diversification floor (5% minimum weight)
   - Single-stock concentration ceiling (20% maximum weight)
   - Step limit (Max ±2.0% change per company per rebalancing cycle)
   - Portfolio turnover limit (Max 10% one-way turnover per cycle)
   - 100% total allocation normalization
4. Water-filling bounded simplex projection algorithm.
5. Historical audit trail and state tracking.
"""

import logging
import math
from typing import Dict, List, Optional
from datetime import datetime, timezone

from src.config import (
    NIFTY_10_BASKET,
    TICKERS,
    EQUAL_WEIGHT,
    MIN_WEIGHT,
    MAX_WEIGHT,
    MAX_CYCLE_MOVEMENT,
    MAX_TURNOVER,
    TILT_ALPHA,
    SOURCE_WEIGHTS
)
from src.engine.models import RiskSignal
from src.rebalancer.models import StockAllocation, PortfolioState, RebalanceHistory

logger = logging.getLogger(__name__)


class IndexRebalancer:
    """
    Main tactical rebalancing engine for the Nifty 10 equity basket.
    """

    def __init__(
        self,
        min_weight: float = MIN_WEIGHT,
        max_weight: float = MAX_WEIGHT,
        max_cycle_movement: float = MAX_CYCLE_MOVEMENT,
        max_turnover: float = MAX_TURNOVER,
        tilt_alpha: float = TILT_ALPHA
    ):
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.max_cycle_movement = max_cycle_movement
        self.max_turnover = max_turnover
        self.tilt_alpha = tilt_alpha

        self.history = RebalanceHistory()
        self.current_state: PortfolioState = self._initialize_equal_weights()
        self.history.states.append(self.current_state)

    # -----------------------------------------------------------------------
    # Portfolio Initialization
    # -----------------------------------------------------------------------

    def _initialize_equal_weights(self) -> PortfolioState:
        """
        Creates the baseline portfolio where all 10 stocks hold exactly 10% (0.10).
        """
        allocations: Dict[str, StockAllocation] = {}
        for ticker in TICKERS:
            info = NIFTY_10_BASKET.get(ticker, {})
            allocations[ticker] = StockAllocation(
                ticker=ticker,
                name=info.get("name", ticker),
                sector=info.get("sector", "Diversified"),
                weight=EQUAL_WEIGHT,
                weight_pct=round(EQUAL_WEIGHT * 100.0, 2),
                sentiment_score=0.0,
                target_weight_raw=EQUAL_WEIGHT,
                delta_weight=0.0
            )

        return PortfolioState(
            allocations=allocations,
            total_weight=1.0,
            turnover=0.0,
            cycle_number=0,
            rebalance_reason="Baseline equal-weight portfolio (10% per constituent)",
            active_signals_count=0,
            signals_applied=[]
        )

    # -----------------------------------------------------------------------
    # Sentiment Aggregation
    # -----------------------------------------------------------------------

    def aggregate_company_sentiments(
        self,
        signals: List[RiskSignal]
    ) -> Dict[str, float]:
        """
        Aggregates risk signals per company using credibility weighting.
        Enforces social-only cap: if only social posts exist, sentiment is clamped to [-0.3, +0.3].
        """
        # Group signals by ticker
        grouped: Dict[str, List[RiskSignal]] = {t: [] for t in TICKERS}
        for sig in signals:
            if sig.ticker in grouped:
                grouped[sig.ticker].append(sig)

        aggregated: Dict[str, float] = {}

        for ticker, sig_list in grouped.items():
            if not sig_list:
                aggregated[ticker] = 0.0
                continue

            # Check if all signals are social media
            all_social = all(s.source == "social" for s in sig_list)

            weighted_sum = 0.0
            weight_total = 0.0

            for s in sig_list:
                src_w = SOURCE_WEIGHTS.get(s.source, 0.5)
                # Combine source weight with signal confidence
                effective_weight = src_w * s.confidence
                weighted_sum += s.sentiment_score * effective_weight
                weight_total += effective_weight

            score = weighted_sum / weight_total if weight_total > 0 else 0.0

            # Social-only sentiment cap to protect from internet rumor storms
            if all_social:
                score = max(-0.3, min(0.3, score))

            aggregated[ticker] = round(max(-1.0, min(1.0, score)), 4)

        return aggregated

    # -----------------------------------------------------------------------
    # Core Rebalancing Calculation
    # -----------------------------------------------------------------------

    def rebalance(
        self,
        signals: List[RiskSignal],
        reason: Optional[str] = None
    ) -> PortfolioState:
        """
        Computes new portfolio allocations based on incoming signals.
        Enforces all institutional constraints:
        1. Exponential tilt
        2. Min/Max bounds [5%, 20%]
        3. Max movement per cycle (±2.0%)
        4. Max portfolio turnover (10%)
        5. Exact 100% sum
        """
        if not signals:
            logger.info("No active signals provided. Portfolio weights unchanged.")
            return self.current_state

        # 1. Aggregate sentiments for all 10 companies
        sentiments = self.aggregate_company_sentiments(signals)

        # 2. Compute Exponential Tilts: Target ∝ 0.10 * exp(alpha * S)
        raw_targets: Dict[str, float] = {}
        for ticker in TICKERS:
            s_i = sentiments.get(ticker, 0.0)
            raw_targets[ticker] = EQUAL_WEIGHT * math.exp(self.tilt_alpha * s_i)

        # Normalize raw targets to sum to 1.0
        sum_raw = sum(raw_targets.values())
        normalized_targets = {t: w / sum_raw for t, w in raw_targets.items()}

        # 3. Determine Effective Upper & Lower Bounds per constituent
        # Combine static [5%, 20%] with cycle movement [prev - 2%, prev + 2%]
        prev_weights = {t: alloc.weight for t, alloc in self.current_state.allocations.items()}
        lower_bounds: Dict[str, float] = {}
        upper_bounds: Dict[str, float] = {}

        for t in TICKERS:
            w_prev = prev_weights[t]
            lower_bounds[t] = max(self.min_weight, w_prev - self.max_cycle_movement)
            upper_bounds[t] = min(self.max_weight, w_prev + self.max_cycle_movement)

        # 4. Water-Filling Bounded Simplex Projection
        # Projects normalized targets onto the constrained hyperplane (sum = 1.0)
        projected_weights = self._project_bounded_simplex(
            targets=normalized_targets,
            lower_bounds=lower_bounds,
            upper_bounds=upper_bounds
        )

        # 5. Enforce Maximum Turnover Constraint
        # Turnover = 0.5 * sum(|w_new - w_prev|)
        initial_turnover = 0.5 * sum(abs(projected_weights[t] - prev_weights[t]) for t in TICKERS)

        final_weights = projected_weights
        final_turnover = initial_turnover

        if initial_turnover > self.max_turnover and initial_turnover > 1e-6:
            # Scale down step size towards prev_weights to respect turnover ceiling
            turnover_scaling = self.max_turnover / initial_turnover
            scaled_weights: Dict[str, float] = {}
            for t in TICKERS:
                delta = projected_weights[t] - prev_weights[t]
                scaled_weights[t] = prev_weights[t] + delta * turnover_scaling
            final_weights = scaled_weights
            final_turnover = 0.5 * sum(abs(final_weights[t] - prev_weights[t]) for t in TICKERS)

        # Final sanity check: ensure weights sum precisely to 1.0000
        total_sum = sum(final_weights.values())
        if abs(total_sum - 1.0) > 1e-6:
            # Micro-adjustment on the highest-weight constituent
            top_ticker = max(final_weights, key=final_weights.get)
            final_weights[top_ticker] += (1.0 - total_sum)

        # 6. Build New Portfolio State
        new_allocations: Dict[str, StockAllocation] = {}
        for t in TICKERS:
            info = NIFTY_10_BASKET.get(t, {})
            w_final = round(final_weights[t], 5)
            w_prev = prev_weights[t]
            delta = round(w_final - w_prev, 5)

            new_allocations[t] = StockAllocation(
                ticker=t,
                name=info.get("name", t),
                sector=info.get("sector", "Diversified"),
                weight=w_final,
                weight_pct=round(w_final * 100.0, 2),
                sentiment_score=sentiments.get(t, 0.0),
                target_weight_raw=round(normalized_targets[t], 5),
                delta_weight=delta
            )

        new_cycle = self.current_state.cycle_number + 1
        rebalance_desc = reason or f"Rebalance Cycle #{new_cycle}: Processed {len(signals)} risk signals"

        new_state = PortfolioState(
            allocations=new_allocations,
            total_weight=round(sum(a.weight for a in new_allocations.values()), 4),
            turnover=round(final_turnover, 5),
            cycle_number=new_cycle,
            rebalance_reason=rebalance_desc,
            active_signals_count=len(signals),
            signals_applied=[s.id for s in signals]
        )

        self.current_state = new_state
        self.history.states.append(new_state)
        return new_state

    # -----------------------------------------------------------------------
    # Optimization Math: Bounded Simplex Projection (Water-Filling)
    # -----------------------------------------------------------------------

    def _project_bounded_simplex(
        self,
        targets: Dict[str, float],
        lower_bounds: Dict[str, float],
        upper_bounds: Dict[str, float],
        max_iterations: int = 50
    ) -> Dict[str, float]:
        """
        Exact iterative water-filling algorithm to project target weights
        subject to:
          1. L_i <= w_i <= U_i for each constituent
          2. sum(w_i) == 1.0
        """
        weights = {t: float(targets[t]) for t in TICKERS}

        for _ in range(max_iterations):
            # Clamp weights to respective bounds
            clamped = {}
            for t in TICKERS:
                clamped[t] = max(lower_bounds[t], min(upper_bounds[t], weights[t]))

            current_sum = sum(clamped.values())
            diff = 1.0 - current_sum

            # If within numerical tolerance, we're done
            if abs(diff) < 1e-7:
                return clamped

            # Identify free constituents that can absorb the difference
            if diff > 0:
                # Need to add weight -> constituents below their upper bound
                free_tickers = [t for t in TICKERS if clamped[t] < upper_bounds[t] - 1e-6]
            else:
                # Need to subtract weight -> constituents above their lower bound
                free_tickers = [t for t in TICKERS if clamped[t] > lower_bounds[t] + 1e-6]

            if not free_tickers:
                # All variables are pinned at bounds
                return clamped

            # Distribute excess evenly among free constituents
            adjustment = diff / len(free_tickers)
            for t in free_tickers:
                weights[t] = clamped[t] + adjustment

        return clamped

    # -----------------------------------------------------------------------
    # Utilities
    # -----------------------------------------------------------------------

    def get_current_portfolio(self) -> PortfolioState:
        """Returns the most recent portfolio snapshot."""
        return self.current_state

    def get_history(self) -> List[PortfolioState]:
        """Returns all historical portfolio states."""
        return self.history.states

    def reset(self) -> PortfolioState:
        """Resets the portfolio back to baseline equal-weights (Cycle 0)."""
        self.history = RebalanceHistory()
        self.current_state = self._initialize_equal_weights()
        self.history.states.append(self.current_state)
        return self.current_state
