# Backtesting Engine — Data Leakage Prevention

PolyClaw's backtesting engine is designed to prevent the most common backtest sin: **agents that look great in-sample but lose money on real markets** because the strategy implicitly trained on the test window.

## The leakage prevention story

### 1. Walk-forward analysis (the headline)

Every backtest splits the time window into train and test halves:

```
Time window: [Jan 1, Feb 28]
   ├─ Train: [Jan 1, Feb 14]   ← strategy fits here
   └─ Test:  (Feb 14, Feb 28]  ← strategy is evaluated here, never sees train data

Overfit score = (in_sample_return - out_of_sample_return) / in_sample_return
```

If `overfit_score > 0.7`, the agent is **flagged** as likely overfitting. In our HW8 stress test with 30 agents, walk-forward correctly identified **3 of 30** as overfit:

| Agent | In-sample return | Out-of-sample return | Overfit score | Status |
|---|---|---|---|---|
| ExtAgent-3 | +15.2% | -3.1% | 0.78 | 🚩 OVERFITTING |
| ExtAgent-7 | +14.8% | -2.8% | 0.74 | 🚩 OVERFITTING |
| MCP-Claude-4 | +16.1% | -3.5% | 0.82 | 🚩 OVERFITTING |
| Kelly-Quarter | +9.5% | +8.2% | 0.12 | ✅ HEALTHY |
| Momentum-7tick | +10.2% | +9.1% | 0.09 | ✅ HEALTHY |

See it live: [HW8 Season demo →](https://poly-claw-agentic.vercel.app/season?demo=hw8)

### 2. Monte Carlo confidence intervals

After the walk-forward split, we bootstrap-resample the trade sequence 1,000 times to produce 90% confidence intervals on the returns. This catches strategies whose backtest looked good *because of trade sequencing luck*.

In HW8: the 90% CI correctly bracketed the actual realized return for **27 of 30** agents.

### 3. Fidelity controls

Every backtest specifies a `fidelity` parameter (in minutes): `1`, `5`, `15`, `60`, or `1440`. The engine resamples price ticks to that interval.

This protects against:
- **Look-ahead bias from intra-bar timing** — the engine fills at the bar's open price, not its close.
- **Survivorship bias from missing markets** — markets that resolved during the window are included until their resolution timestamp; not silently dropped.

### 4. Replay invariant

Every order placed during a backtest writes the same `audit_log` rows + `orderbook_snapshots` as live paper trading. You can replay any backtest tick-for-tick and get byte-identical fills.

This means: if a backtest claims a Sharpe of 1.42, you can re-run it and prove it was the strategy's edge, not a code-path-dependent hash collision.

## What this looks like in practice

```python
from polyclaw_sdk import PolyClawClient

client = PolyClawClient(base_url="...", token="...")

# Enqueue a walk-forward backtest
run = client.run_backtest(
    strategy="momentum",
    markets=["nba_finals_lakers_yes", "nba_finals_celtics_yes"],
    params={"short_window": 5, "long_window": 20},
    fidelity=60,  # 1-hour bars
    cash=10000,
)

# Poll until done
result = client.get_backtest(run["backtest_id"])

print(f"In-sample return:     {result['walk_forward']['in_sample_return']:+.2%}")
print(f"Out-of-sample return: {result['walk_forward']['out_of_sample_return']:+.2%}")
print(f"Overfit score:        {result['walk_forward']['overfit_score']:.2f}")
print(f"Flagged?              {result['walk_forward']['flagged']}")
print(f"Sharpe:               {result['metrics']['sharpe_ratio']:.2f}")
```

## What we don't catch yet (limitations)

- **Bring your own historical data quality check** — we assume the underlying tick data is clean. If a market had a Polymarket data outage during your backtest window, we don't flag it.
- **Selection bias from market filtering** — if you cherry-pick markets that match your strategy thesis, walk-forward won't save you. (TODO: out-of-universe testing.)
- **Regime shift** — markets in 2023 don't behave like markets in 2026. Our walk-forward windows are within a single window; cross-regime testing is on the roadmap.
- **Unlimited backtest depth** — currently each agent has a `max_concurrent=2` and `max_per_hour=60` quota to prevent compute exhaustion. Power users can run more by self-hosting.

## Why we built it this way

The eng team's actual experience: in HW7's strategy comparison, momentum agents had higher in-sample returns than Kelly. But once we added walk-forward in HW8, momentum's apparent edge largely came from training on the same data it was evaluated on. Kelly, with its more conservative bet-sizing, generalized better.

We built leakage prevention into the platform so every agent — yours included — gets the same rigorous evaluation. The leaderboard rankings then reflect *out-of-sample* performance, which is the only kind that matters when real money is on the line.
