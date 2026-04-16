"""Backtest worker loop — Phase 2c.

One long-running process that drives two independent loops:

1. **Backtest loop.** Polls `backtest_runs` every `BACKTEST_POLL_INTERVAL_S` for
   a claimed run, hydrates the strategy + market data, runs the `BacktestEngine`,
   writes the result/error blob back to the row.

2. **Portfolio sampler loop.** Every `SAMPLER_INTERVAL_S`, iterates every active
   agent in the `agents` table and calls `PaperTrader.sample_portfolio()` so
   the equity curve gets a tick even during idle periods (trades already write
   a snapshot inline, this loop covers the in-between).

Both loops run on separate threads inside one process. Graceful shutdown: SIGTERM
sets a `stop` event, both loops observe it between iterations and exit cleanly.

Deployment target: Railway single always-on instance (PLAN §7.2c). Local dev runs
via `python -m polyclaw.workers.backtest_worker` or `docker compose up worker`.
"""

from __future__ import annotations

import logging
import signal
import threading
from typing import Any

from sqlalchemy import Engine, select

from polyclaw.agents.portfolio_manager import PortfolioManager
from polyclaw.backtest.data_loader import DataLoader, PostgresSource
from polyclaw.backtest.engine import BacktestEngine
from polyclaw.backtest.strategies import get_strategy
from polyclaw.storage.schema import agents
from polyclaw.trading.clock import Clock, SystemClock
from polyclaw.trading.market_data import LiveMarketDataProvider, MarketDataProvider
from polyclaw.workers.backtest_queue import BacktestClaim, BacktestQueue

logger = logging.getLogger(__name__)


#: How often the backtest loop polls the queue when idle. PLAN §7.2c sets 2s.
BACKTEST_POLL_INTERVAL_S = 2.0

#: How often the portfolio-snapshot sampler fires per-agent. PLAN §7.2c sets 60s.
SAMPLER_INTERVAL_S = 60.0


class BacktestWorker:
    """One worker per process. Owns both loops + their stop event.

    Construct with a shared `Engine`; the portfolio sampler uses its own
    `PortfolioManager` instance so cached PaperTraders don't cross-contaminate
    with whatever else is holding the engine.
    """

    def __init__(
        self,
        engine: Engine,
        *,
        clock: Clock | None = None,
        market_data: MarketDataProvider | None = None,
        backtest_poll_interval_s: float = BACKTEST_POLL_INTERVAL_S,
        sampler_interval_s: float = SAMPLER_INTERVAL_S,
    ):
        self.engine = engine
        self.clock: Clock = clock or SystemClock()
        self.market_data: MarketDataProvider = market_data or LiveMarketDataProvider()
        self.queue = BacktestQueue(engine, clock=self.clock)
        self.portfolios = PortfolioManager(engine=engine, clock=self.clock, market_data=self.market_data)
        self.backtest_poll_interval_s = backtest_poll_interval_s
        self.sampler_interval_s = sampler_interval_s
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # ── Lifecycle ─────────────────────────────────────────────

    def run_forever(self) -> None:
        """Start both loops and block until SIGTERM / SIGINT. For running under
        Railway's process supervisor or docker-compose."""
        signal.signal(signal.SIGTERM, lambda *_: self.stop())
        signal.signal(signal.SIGINT, lambda *_: self.stop())
        self.start()
        try:
            while not self._stop.is_set():
                self._stop.wait(1.0)
        finally:
            self.join()

    def start(self) -> None:
        """Start the two loops on separate threads. Returns immediately."""
        self._stop.clear()
        t1 = threading.Thread(target=self._backtest_loop, name="backtest-worker", daemon=True)
        t2 = threading.Thread(target=self._sampler_loop, name="sampler-worker", daemon=True)
        self._threads = [t1, t2]
        for t in self._threads:
            t.start()
        logger.info(
            "worker started: backtest_poll=%.1fs sampler_interval=%.1fs",
            self.backtest_poll_interval_s,
            self.sampler_interval_s,
        )

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: float | None = 5.0) -> None:
        for t in self._threads:
            t.join(timeout=timeout)

    # ── Backtest loop ─────────────────────────────────────────

    def _backtest_loop(self) -> None:
        while not self._stop.is_set():
            try:
                claim = self.queue.claim_one()
            except Exception as e:
                logger.exception("claim_one raised: %s", e)
                self._stop.wait(self.backtest_poll_interval_s)
                continue

            if claim is None:
                self._stop.wait(self.backtest_poll_interval_s)
                continue

            self._run_one(claim)

    def _run_one(self, claim: BacktestClaim) -> None:
        logger.info(
            "running backtest %s strategy=%s markets=%d", claim.id, claim.strategy, len(claim.markets)
        )
        try:
            strategy = get_strategy(claim.strategy)
            if claim.params:
                strategy.configure(claim.params)
        except Exception as e:
            self.queue.mark_failed(claim.id, {"type": "unknown_strategy", "message": str(e)})
            return

        try:
            loader = DataLoader(source=PostgresSource(self.engine))
            market_data = []
            for m in claim.markets:
                token_id = m["token_id"]
                try:
                    data = loader.load_market_prices(
                        token_id=token_id,
                        market_id=m.get("market_id", ""),
                        market_question=m.get("question", ""),
                        outcome=m.get("outcome", "Yes"),
                        fidelity=claim.fidelity,
                    )
                    if data.ticks:
                        market_data.append(data)
                except Exception as e:
                    logger.warning("skip %s: %s", token_id[:20], e)

            if not market_data:
                self.queue.mark_failed(
                    claim.id,
                    {
                        "type": "no_market_data",
                        "message": "No price_ticks available for any requested token. "
                        "Backfill via ingestion.backfill_price_ticks first.",
                    },
                )
                return

            # Check for advanced options in params
            walk_forward_opts = claim.params.pop("walk_forward", None) if claim.params else None
            monte_carlo_opts = claim.params.pop("monte_carlo", None) if claim.params else None
            optimize_opts = claim.params.pop("optimize", None) if claim.params else None

            if optimize_opts:
                from polyclaw.backtest.advanced import run_param_optimization

                opt_result = run_param_optimization(
                    claim.strategy,
                    market_data,
                    param_grid=optimize_opts.get("param_grid", {}),
                    starting_cash=claim.cash,
                    metric=optimize_opts.get("metric", "sharpe"),
                )
                output: dict[str, Any] = {
                    "type": "optimization",
                    "total_combos": opt_result.total_combos,
                    "best": {
                        "params": opt_result.best.params,
                        "return_pct": opt_result.best.return_pct,
                        "sharpe": opt_result.best.sharpe,
                    }
                    if opt_result.best
                    else None,
                    "heatmap_data": opt_result.heatmap_data[:200],
                }
                self.queue.mark_finished(claim.id, output)
            else:
                engine = BacktestEngine(starting_cash=claim.cash)
                result = engine.run(strategy, market_data)
                output = self._serialize_result(result)

                if walk_forward_opts:
                    from polyclaw.backtest.advanced import run_walk_forward

                    wf = run_walk_forward(
                        claim.strategy,
                        market_data,
                        params=claim.params,
                        n_splits=walk_forward_opts.get("n_splits", 5),
                        train_pct=walk_forward_opts.get("train_pct", 0.7),
                        starting_cash=claim.cash,
                    )
                    output["walk_forward"] = {
                        "splits": [
                            {"train_return": s.train_return, "test_return": s.test_return} for s in wf.splits
                        ],
                        "aggregate_train_return": wf.aggregate_train_return,
                        "aggregate_test_return": wf.aggregate_test_return,
                        "overfit_score": wf.overfit_score,
                        "is_overfitting": wf.is_overfitting,
                    }

                if monte_carlo_opts:
                    from polyclaw.backtest.advanced import run_monte_carlo

                    mc = run_monte_carlo(
                        result,
                        n_simulations=monte_carlo_opts.get("n_simulations", 1000),
                        ruin_threshold_pct=monte_carlo_opts.get("ruin_threshold_pct", -50.0),
                        seed=monte_carlo_opts.get("seed"),
                    )
                    output["monte_carlo"] = {
                        "n_simulations": mc.n_simulations,
                        "median_return": mc.median_return,
                        "p5_return": mc.p5_return,
                        "p95_return": mc.p95_return,
                        "mean_return": mc.mean_return,
                        "probability_of_ruin": mc.probability_of_ruin,
                        "distribution": mc.distribution[:200],  # trim for DB
                    }

                self.queue.mark_finished(claim.id, output)
            logger.info("finished backtest %s", claim.id)

        except Exception as e:
            logger.exception("backtest %s failed: %s", claim.id, e)
            self.queue.mark_failed(claim.id, {"type": type(e).__name__, "message": str(e)})

    @staticmethod
    def _serialize_result(result: Any) -> dict[str, Any]:
        """Convert BacktestResult to a JSON-serializable dict. Pulls just the
        metrics + trimmed equity curve; full trade lists would bloat the row."""
        data = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        # Trim equity curve to at most ~200 points to keep the result row bounded
        equity = data.get("equity_curve", [])
        if len(equity) > 200:
            step = len(equity) // 200
            data["equity_curve"] = equity[::step]
        return data

    # ── Portfolio sampler loop ────────────────────────────────

    def _sampler_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._sample_all_agents()
            except Exception as e:
                logger.exception("sampler loop iteration failed: %s", e)
            self._stop.wait(self.sampler_interval_s)

    def _sample_all_agents(self) -> None:
        with self.engine.connect() as conn:
            rows = conn.execute(select(agents.c.id).where(agents.c.status == "active")).all()
        for (agent_id,) in rows:
            try:
                trader = self.portfolios.trader_for(agent_id)
                trader.sample_portfolio()
            except Exception as e:
                logger.warning("sampler skip agent=%s: %s", agent_id, e)

        # Season lifecycle auto-tick (start/finalize based on clock)
        try:
            from polyclaw.seasons.engine import SeasonEngine

            se = SeasonEngine(self.engine, clock=self.clock)
            se.tick()
        except Exception as e:
            logger.warning("season tick failed: %s", e)

        # Safety circuit breakers for live-approved agents
        try:
            from polyclaw.trading.safety import SafetyMonitor

            monitor = SafetyMonitor(self.engine, clock=self.clock)
            paused = monitor.check_all_agents()
            if paused:
                logger.warning("safety paused agents: %s", paused)
        except Exception as e:
            logger.warning("safety check failed: %s", e)


# ── CLI entrypoint ────────────────────────────────────────────────────────


def main() -> int:  # pragma: no cover — CLI shim
    import os

    logging.basicConfig(
        level=os.environ.get("POLYCLAW_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from polyclaw.storage.db import make_engine

    url = os.environ.get("POLYCLAW_DATABASE_URL") or "sqlite:///paper_trading.db"
    engine = make_engine(url)
    worker = BacktestWorker(engine)
    worker.run_forever()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
