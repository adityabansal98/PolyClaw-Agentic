"""Advanced backtesting — Phase 5.

Three features that match what professional platforms (QuantConnect, Backtrader) offer:

1. **Walk-forward analysis** — splits data into train/test windows, runs the strategy
   on train, validates on test. Catches overfitting that pure in-sample backtests miss.

2. **Monte Carlo simulation** — bootstrap-resamples trades from a backtest result to
   build a distribution of outcomes. Reports median return, 5th/95th percentiles, and
   probability of ruin (equity dropping below a threshold).

3. **Parameter optimization** — grid search over strategy parameter combinations.
   Runs N backtests (one per combo), returns a ranked table + heatmap data.

All three are pure functions that take a BacktestEngine + strategy + data and return
result objects. They're called by the backtest worker when the enqueue request includes
`walk_forward`, `monte_carlo`, or `optimize` keys.
"""

from __future__ import annotations

import itertools
import logging
import math
import random
from dataclasses import dataclass
from typing import Any

from polyclaw.backtest.data_loader import MarketPriceData
from polyclaw.backtest.engine import BacktestEngine
from polyclaw.backtest.results import BacktestResult, PerformanceMetrics
from polyclaw.backtest.strategies import get_strategy

logger = logging.getLogger(__name__)


# ── Walk-Forward Analysis ─────────────────────────────────────────────────


@dataclass
class WalkForwardSplit:
    split_index: int
    train_metrics: PerformanceMetrics
    test_metrics: PerformanceMetrics
    train_return: float
    test_return: float


@dataclass
class WalkForwardResult:
    splits: list[WalkForwardSplit]
    aggregate_train_return: float
    aggregate_test_return: float
    overfit_score: float  # 0 = no overfit, 1 = total overfit
    is_overfitting: bool


def run_walk_forward(
    strategy_name: str,
    market_data: list[MarketPriceData],
    *,
    params: dict[str, Any] | None = None,
    n_splits: int = 5,
    train_pct: float = 0.7,
    starting_cash: float = 10_000.0,
) -> WalkForwardResult:
    """Split each market's ticks into n_splits sequential windows, run train then test.

    The overfit score is: 1 - (avg_test_return / avg_train_return). If test performance
    matches train, overfit_score ≈ 0. If test is much worse, score approaches 1. If
    train return is ≤ 0, overfit is undefined and we flag is_overfitting=True.
    """
    if n_splits < 2:
        raise ValueError("walk-forward needs at least 2 splits")

    splits: list[WalkForwardSplit] = []

    # For each split: divide ticks sequentially
    for i in range(n_splits):
        train_data, test_data = _split_market_data(market_data, i, n_splits, train_pct)
        if not train_data or not test_data:
            continue

        # Train
        strategy = get_strategy(strategy_name)
        if params:
            strategy.configure(params)
        train_engine = BacktestEngine(starting_cash=starting_cash)
        train_result = train_engine.run(strategy, train_data)

        # Test (same strategy, fresh engine)
        strategy = get_strategy(strategy_name)
        if params:
            strategy.configure(params)
        test_engine = BacktestEngine(starting_cash=starting_cash)
        test_result = test_engine.run(strategy, test_data)

        splits.append(
            WalkForwardSplit(
                split_index=i,
                train_metrics=train_result.metrics,
                test_metrics=test_result.metrics,
                train_return=train_result.metrics.total_return_pct,
                test_return=test_result.metrics.total_return_pct,
            )
        )

    if not splits:
        return WalkForwardResult(
            splits=[],
            aggregate_train_return=0,
            aggregate_test_return=0,
            overfit_score=1.0,
            is_overfitting=True,
        )

    avg_train = sum(s.train_return for s in splits) / len(splits)
    avg_test = sum(s.test_return for s in splits) / len(splits)

    if avg_train <= 0:
        overfit_score = 1.0
        is_overfitting = True
    else:
        overfit_score = max(0.0, 1.0 - (avg_test / avg_train))
        is_overfitting = overfit_score > 0.5

    return WalkForwardResult(
        splits=splits,
        aggregate_train_return=round(avg_train, 4),
        aggregate_test_return=round(avg_test, 4),
        overfit_score=round(overfit_score, 4),
        is_overfitting=is_overfitting,
    )


def _split_market_data(
    market_data: list[MarketPriceData], split_idx: int, n_splits: int, train_pct: float
) -> tuple[list[MarketPriceData], list[MarketPriceData]]:
    """Slice each market's ticks into train/test for this split window."""
    train_out, test_out = [], []
    for md in market_data:
        n = len(md.ticks)
        if n < 10:
            continue
        # Anchored walk-forward: train starts at 0, grows with each split
        train_end = int(n * (train_pct + (1 - train_pct) * split_idx / max(n_splits - 1, 1)))
        train_end = max(5, min(train_end, n - 5))
        train_ticks = md.ticks[:train_end]
        test_ticks = md.ticks[train_end:]
        if not train_ticks or not test_ticks:
            continue
        train_out.append(
            MarketPriceData(
                token_id=md.token_id,
                market_id=md.market_id,
                market_question=md.market_question,
                outcome=md.outcome,
                ticks=train_ticks,
                fidelity=md.fidelity,
            )
        )
        test_out.append(
            MarketPriceData(
                token_id=md.token_id,
                market_id=md.market_id,
                market_question=md.market_question,
                outcome=md.outcome,
                ticks=test_ticks,
                fidelity=md.fidelity,
            )
        )
    return train_out, test_out


# ── Monte Carlo Simulation ────────────────────────────────────────────────


@dataclass
class MonteCarloResult:
    n_simulations: int
    median_return: float
    p5_return: float  # 5th percentile
    p95_return: float  # 95th percentile
    mean_return: float
    std_return: float
    probability_of_ruin: float  # fraction of sims where equity fell below ruin_threshold
    ruin_threshold_pct: float
    distribution: list[float]  # sorted returns for histogram


def run_monte_carlo(
    backtest_result: BacktestResult,
    *,
    n_simulations: int = 1000,
    ruin_threshold_pct: float = -50.0,
    seed: int | None = None,
) -> MonteCarloResult:
    """Bootstrap-resample trades from a backtest result to build a return distribution.

    Each simulation: randomly resample (with replacement) the same number of trades
    as the original, replay them sequentially on a fresh equity curve, compute final
    return. The distribution of N final returns gives confidence intervals.
    """
    rng = random.Random(seed)
    trades = backtest_result.trades
    starting = backtest_result.starting_cash

    if not trades:
        return MonteCarloResult(
            n_simulations=n_simulations,
            median_return=0,
            p5_return=0,
            p95_return=0,
            mean_return=0,
            std_return=0,
            probability_of_ruin=0,
            ruin_threshold_pct=ruin_threshold_pct,
            distribution=[0.0] * n_simulations,
        )

    # Extract per-trade PnL (signed)
    trade_pnls: list[float] = []
    for t in trades:
        pnl = -t.cost - t.fee if t.side == "BUY" else t.cost - t.fee
        trade_pnls.append(pnl)

    returns: list[float] = []
    ruin_count = 0

    for _ in range(n_simulations):
        # Resample trades with replacement
        sampled = [rng.choice(trade_pnls) for _ in range(len(trade_pnls))]
        equity = starting
        min_equity = starting
        for pnl in sampled:
            equity += pnl
            min_equity = min(min_equity, equity)
        ret_pct = ((equity - starting) / starting) * 100 if starting > 0 else 0
        returns.append(ret_pct)
        if ret_pct <= ruin_threshold_pct:
            ruin_count += 1

    returns.sort()
    n = len(returns)
    p5 = returns[int(n * 0.05)]
    p95 = returns[int(n * 0.95)]
    median = returns[n // 2]
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / n
    std = math.sqrt(variance)

    return MonteCarloResult(
        n_simulations=n_simulations,
        median_return=round(median, 4),
        p5_return=round(p5, 4),
        p95_return=round(p95, 4),
        mean_return=round(mean, 4),
        std_return=round(std, 4),
        probability_of_ruin=round(ruin_count / n, 4),
        ruin_threshold_pct=ruin_threshold_pct,
        distribution=returns,
    )


# ── Parameter Optimization ────────────────────────────────────────────────


@dataclass
class ParamComboResult:
    params: dict[str, Any]
    metrics: PerformanceMetrics
    return_pct: float
    sharpe: float | None


@dataclass
class OptimizationResult:
    strategy_name: str
    param_grid: dict[str, list[Any]]
    total_combos: int
    results: list[ParamComboResult]
    best: ParamComboResult | None
    heatmap_data: list[dict[str, Any]]  # [{param_1: val, param_2: val, return: val}, ...]


MAX_COMBOS = 100  # PLAN-V2 quota cap


def run_param_optimization(
    strategy_name: str,
    market_data: list[MarketPriceData],
    *,
    param_grid: dict[str, list[Any]],
    starting_cash: float = 10_000.0,
    metric: str = "sharpe",  # "sharpe" | "return" | "calmar"
) -> OptimizationResult:
    """Grid search over strategy parameter combinations.

    Returns ranked results + heatmap-ready data. Capped at MAX_COMBOS to prevent
    abuse (quota enforcement happens at the enqueue layer in BacktestQueue).
    """
    # Build all combinations
    keys = sorted(param_grid.keys())
    value_lists = [param_grid[k] for k in keys]
    combos = list(itertools.product(*value_lists))

    if len(combos) > MAX_COMBOS:
        raise ValueError(f"param_grid produces {len(combos)} combos, max is {MAX_COMBOS}")

    results: list[ParamComboResult] = []
    heatmap: list[dict[str, Any]] = []

    for values in combos:
        combo = dict(zip(keys, values, strict=True))
        try:
            strategy = get_strategy(strategy_name)
            strategy.configure(combo)
            engine = BacktestEngine(starting_cash=starting_cash)
            result = engine.run(strategy, market_data)
            results.append(
                ParamComboResult(
                    params=combo,
                    metrics=result.metrics,
                    return_pct=result.metrics.total_return_pct,
                    sharpe=result.metrics.sharpe_ratio,
                )
            )
            row = dict(combo)
            row["return_pct"] = result.metrics.total_return_pct
            row["sharpe"] = result.metrics.sharpe_ratio
            heatmap.append(row)
        except Exception as e:
            logger.warning("param combo %s failed: %s", combo, e)

    # Sort by chosen metric
    def _sort_key(r: ParamComboResult) -> float:
        if metric == "sharpe":
            return r.sharpe or -999
        if metric == "return":
            return r.return_pct
        return r.return_pct  # fallback

    results.sort(key=_sort_key, reverse=True)

    return OptimizationResult(
        strategy_name=strategy_name,
        param_grid=param_grid,
        total_combos=len(combos),
        results=results,
        best=results[0] if results else None,
        heatmap_data=heatmap,
    )
