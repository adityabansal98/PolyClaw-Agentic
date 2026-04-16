"""Phase 5 tests — walk-forward, Monte Carlo, parameter optimization."""

from __future__ import annotations

import pytest

from polyclaw.backtest.advanced import (
    MAX_COMBOS,
    run_monte_carlo,
    run_param_optimization,
    run_walk_forward,
)
from polyclaw.backtest.data_loader import MarketPriceData
from polyclaw.backtest.engine import BacktestEngine
from polyclaw.backtest.results import BacktestResult
from polyclaw.backtest.strategies import get_strategy


def _sample_ticks(n: int = 200, base: float = 0.5, volatility: float = 0.02) -> list[tuple[int, float]]:
    """Generate n synthetic ticks with simple random walk."""
    import random

    rng = random.Random(42)
    ticks = []
    price = base
    for i in range(n):
        price = max(0.01, price + rng.gauss(0, volatility))
        ticks.append((1_700_000_000_000 + i * 60_000, round(price, 6)))
    return ticks


def _sample_market_data(n_ticks: int = 200) -> list[MarketPriceData]:
    return [
        MarketPriceData(
            token_id="tok1",
            market_id="mkt1",
            market_question="Test market",
            outcome="Yes",
            ticks=_sample_ticks(n_ticks),
            fidelity=60,
        )
    ]


def _run_basic_backtest(market_data: list[MarketPriceData] | None = None) -> BacktestResult:
    md = market_data or _sample_market_data()
    strategy = get_strategy("momentum")
    engine = BacktestEngine(starting_cash=1_000.0)
    return engine.run(strategy, md)


# ── Walk-Forward ──────────────────────────────────────────────────────────


def test_walk_forward_produces_splits():
    result = run_walk_forward(
        "momentum",
        _sample_market_data(300),
        n_splits=3,
        train_pct=0.6,
        starting_cash=1_000.0,
    )
    assert len(result.splits) == 3
    for s in result.splits:
        # Each split has train and test returns (may be 0 if no trades)
        assert isinstance(s.train_return, float)
        assert isinstance(s.test_return, float)
    assert 0.0 <= result.overfit_score <= 1.0


def test_walk_forward_needs_minimum_splits():
    with pytest.raises(ValueError, match="at least 2"):
        run_walk_forward("momentum", _sample_market_data(), n_splits=1)


def test_walk_forward_overfit_detection():
    """With enough data, walk-forward should produce a meaningful overfit score.
    We can't guarantee it detects overfitting on random data, but it should run
    without error and produce a score in [0, 1]."""
    result = run_walk_forward(
        "momentum",
        _sample_market_data(500),
        n_splits=5,
        starting_cash=1_000.0,
    )
    assert 0.0 <= result.overfit_score <= 1.0
    assert isinstance(result.is_overfitting, bool)


# ── Monte Carlo ───────────────────────────────────────────────────────────


def test_monte_carlo_produces_distribution():
    bt = _run_basic_backtest()
    mc = run_monte_carlo(bt, n_simulations=500, seed=42)
    assert mc.n_simulations == 500
    assert len(mc.distribution) == 500
    # Distribution is sorted
    assert mc.distribution == sorted(mc.distribution)
    # Percentiles are ordered
    assert mc.p5_return <= mc.median_return <= mc.p95_return


def test_monte_carlo_deterministic_with_seed():
    bt = _run_basic_backtest()
    mc1 = run_monte_carlo(bt, n_simulations=100, seed=123)
    mc2 = run_monte_carlo(bt, n_simulations=100, seed=123)
    assert mc1.distribution == mc2.distribution
    assert mc1.median_return == mc2.median_return


def test_monte_carlo_probability_of_ruin():
    bt = _run_basic_backtest()
    # With a very tight ruin threshold, probability should be high
    mc_tight = run_monte_carlo(bt, n_simulations=500, ruin_threshold_pct=50.0, seed=42)
    # With a very loose threshold, probability should be low
    mc_loose = run_monte_carlo(bt, n_simulations=500, ruin_threshold_pct=-99.0, seed=42)
    assert mc_loose.probability_of_ruin <= mc_tight.probability_of_ruin


def test_monte_carlo_empty_trades():
    """Monte Carlo with no trades should return zeros, not crash."""
    from polyclaw.backtest.results import PerformanceMetrics

    bt = BacktestResult(
        backtest_id="test",
        strategy_name="momentum",
        started_at="",
        finished_at="",
        starting_cash=1000,
        ending_cash=1000,
        ending_equity=1000,
        fee_bps=0,
        fidelity=60,
        markets=[],
        trades=[],
        equity_curve=[],
        metrics=PerformanceMetrics(
            total_return_pct=0,
            total_return_usd=0,
            sharpe_ratio=None,
            max_drawdown_pct=0,
            max_drawdown_usd=0,
            win_rate=0,
            profit_factor=None,
            avg_trade_pnl=0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            avg_win=0,
            avg_loss=0,
            best_trade_pnl=0,
            worst_trade_pnl=0,
            total_fees_paid=0,
        ),
        strategy_params={},
    )
    mc = run_monte_carlo(bt, n_simulations=50, seed=1)
    assert mc.median_return == 0
    assert mc.probability_of_ruin == 0


# ── Parameter Optimization ────────────────────────────────────────────────


def test_param_optimization_grid_search():
    md = _sample_market_data(200)
    result = run_param_optimization(
        "momentum",
        md,
        param_grid={"short_window": [5, 10], "long_window": [20, 30]},
        starting_cash=1_000.0,
    )
    assert result.total_combos == 4  # 2 * 2
    assert len(result.results) <= 4  # some may fail
    assert result.best is not None
    assert len(result.heatmap_data) == len(result.results)
    # Results are ranked (first is best)
    if len(result.results) >= 2:
        assert (result.results[0].sharpe or -999) >= (result.results[1].sharpe or -999)


def test_param_optimization_quota_cap():
    md = _sample_market_data(50)
    # Grid that produces > MAX_COMBOS
    big_grid = {"p1": list(range(20)), "p2": list(range(20))}  # 400 combos
    assert MAX_COMBOS < 20 * 20
    with pytest.raises(ValueError, match="max is"):
        run_param_optimization("momentum", md, param_grid=big_grid)


def test_param_optimization_single_param():
    md = _sample_market_data(200)
    result = run_param_optimization(
        "momentum",
        md,
        param_grid={"short_window": [3, 5, 10, 15]},
    )
    assert result.total_combos == 4
    assert result.best is not None
