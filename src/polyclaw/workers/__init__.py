"""Background workers — Phase 2c.

One process, two loops:
- `backtest_worker.run_forever` polls `backtest_runs` every ~2s and executes
  any claimed run through `BacktestEngine`.
- Same process drives the `portfolio_snapshots` sampler every 60s across all
  active agents.

Both loops are cooperative, run on one thread each, and share the same
SQLAlchemy `Engine`. Deployment target: Railway single always-on instance per
PLAN.md §7.2c. Docker-compose brings it up locally alongside the API.
"""
