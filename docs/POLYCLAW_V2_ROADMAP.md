# PolyClaw v2: Professional Trading Platform + AutoResearch Roadmap

## Executive Summary

PolyClaw v2 transforms the current prototype into a professional-grade prediction market trading platform with three major upgrades:

1. **Professional Backtesting Dashboard** — interactive charts, hover details, trade markers, strategy comparison
2. **Enhanced Opportunities Page** — sparklines, edge visualization, Kelly sizing, risk/reward in plain English
3. **AutoResearch Engine** — Karpathy-inspired autonomous strategy discovery loop that continuously finds alpha

---

## Problems to Solve

### 1. Backtesting UI is unintuitive
- Can't hover on chart to see exact values (price, equity, PnL at any point)
- No benchmark comparison (how would buy-and-hold have done?)
- No per-trade PnL coloring on the chart (green/red markers)
- Metrics are just numbers with no context ("is 1.42 Sharpe good?")
- No way to compare strategies side-by-side
- Charts are static SVG — no zoom, pan, or interaction

### 2. Opportunities page lacks depth
- No explanation of WHY a bet is recommended
- No historical price chart for each market
- Edge/confidence numbers feel arbitrary without context
- Kelly sizing not surfaced to user
- No "what happens if I bet $X" simulator

### 3. No continuous strategy discovery
- Strategies are static (coded once, never improved)
- No system to autonomously discover new edges
- No external data integration beyond Polymarket
- No feedback loop from backtest results to strategy improvement

---

## Part 1: Professional Backtesting Dashboard

*Inspired by QuantConnect, TradingView Strategy Tester, and PolyBackTest*

### 1A. Interactive Charts with Recharts

Replace static SVG with [recharts](https://recharts.org/) (lightweight React charting library).

**Equity Curve Chart:**
- Line chart with hover crosshair showing exact date, equity, daily return %
- Green/red shading above/below starting capital line
- Trade markers: green triangles (BUY) and red triangles (SELL) on the curve
- Benchmark line: "buy and hold at first price" comparison
- Time range selector: 1W, 1M, 3M, ALL with click-to-zoom
- Y-axis: dollar values. X-axis: dates.

**Drawdown Chart:**
- Area chart (red fill) showing underwater equity curve
- Hover shows: drawdown %, duration, recovery time
- Annotation: mark worst drawdown period with a highlight band

**Per-Trade PnL Chart:**
- Bar chart: each bar = one round-trip trade
- Green bars = profitable, red bars = loss
- Height = dollar PnL
- Hover shows: market question, entry/exit price, PnL, holding period

### 1B. Enhanced KPI Cards with Context

Each KPI card shows not just the number but context:

| KPI | Value | Context shown |
|-----|-------|--------------|
| Total Return | +12.3% | "vs. buy-and-hold: +3.1%" with comparison arrow |
| Sharpe Ratio | 1.42 | Color-coded bar: <0 red, 0-1 yellow, 1-2 green, 2+ gold |
| Max Drawdown | -8.5% | "Recovery: 12 days" + mini sparkline |
| Win Rate | 58% | "29W / 21L" with win/loss bar |
| Profit Factor | 1.85 | "Every $1 lost earned $1.85" plain English |
| Avg Hold Time | 4.2 hrs | Shows typical trade duration |

### 1C. Strategy Comparison Mode

Add a "Compare" button that runs 2-3 strategies on the same markets and shows:
- Overlaid equity curves (different colors)
- Side-by-side metric cards
- Table: strategy A vs B vs C with key metrics
- Winner badge on the best-performing strategy

### 1D. Trade Details Panel

Click any trade in the log to expand:
- Mini price chart around that trade (5 ticks before, 5 after)
- Entry/exit arrows on the chart
- Dollar PnL prominently displayed
- Strategy's reason for entering/exiting
- "If you had held longer..." counterfactual

### 1E. "What If" Simulator

Before running a backtest, show estimated outcomes:
- "With $10K on threshold strategy across 5 NBA markets..."
- Expected range based on similar historical runs
- Risk warning: "Backtests overstate returns ~10x vs live trading"

---

## Part 2: Enhanced Opportunities Page

### 2A. Market Deep Dive Cards

Each opportunity card should show:
- **Price chart**: mini sparkline of last 30 days (already have price history API)
- **Why this bet**: 1-sentence AI-generated explanation (already have `ai_commentary`)
- **Kelly stake**: "Bet $64 (0.64% of bankroll)" with confidence level
- **Risk/reward**: "Risk $64 to potentially win $1,536 if YES resolves"
- **Edge breakdown**: visual bar showing model vs market probability
- **Polymarket link**: direct link to trade on Polymarket

### 2B. Edge Visualization

Replace raw numbers with intuitive visuals:
- **Edge meter**: horizontal bar showing market price vs model price
  - Left end: 0%, right end: 100%
  - Market price marker (dot) vs Model price marker (triangle)
  - Gap between them = edge (highlighted)
- **Confidence gauge**: semicircle gauge (0-100%) with color zones

### 2C. Category Insights Header

Top of opportunities page shows per-category stats:
- NBA: "3 opportunities, avg edge 4.2%, top: Cavaliers Finals YES"
- Soccer: "5 opportunities, avg edge 2.1%, top: Arsenal EPL YES"
- Each with a category-specific insight (e.g., "B2B games tonight" for NBA)

---

## Part 3: AutoResearch — Continuous Strategy Discovery

*Adapted from [Andrej Karpathy's autoresearch](https://github.com/karpathy/autoresearch) (66K+ GitHub stars)*

Karpathy's pattern: an AI agent runs an indefinite loop — propose a change, run an experiment, check if the result improved, keep or discard, repeat. His 630-line script ran 700 experiments in 2 days and stacked 20 additive improvements.

### 3A. Architecture

Our adaptation for trading strategies:

```
LOOP forever:
  1. RESEARCH: Search the web for new trading strategies, signals, data sources
  2. PROPOSE: LLM generates a new Strategy class (Python code)
  3. BACKTEST: Run the strategy against historical Polymarket data
  4. EVALUATE: Compare metrics (Sharpe, return, drawdown) to current best
  5. KEEP/DISCARD: If better → save to strategy registry. If worse → log and discard.
  6. REPORT: Update a leaderboard of all tested strategies
  7. REPEAT
```

### 3B. Research Agent

**`src/polyclaw/research/agent.py`**

An autonomous agent that:
1. Searches the web for Polymarket trading strategies (Reddit, Medium, arXiv, Twitter)
2. Extracts actionable ideas (buy signals, data sources, timing patterns)
3. Converts ideas into Strategy class code using LLM (OpenAI API)
4. Backtests each strategy across multiple market categories
5. Keeps a log of all experiments with results
6. Proposes variations on winning strategies (parameter tuning, signal combinations)

### 3C. Experiment Loop

**`src/polyclaw/research/experiment_loop.py`**

```python
class ExperimentLoop:
    """Karpathy-inspired autoresearch for trading strategies."""
    
    def __init__(self, research_directions: str):
        self.directions = research_directions  # like program.md
        self.best_sharpe = -999
        self.best_strategy = None
        self.experiment_log = []
    
    def run(self, num_experiments: int = 50):
        for i in range(num_experiments):
            # 1. Propose a strategy variation
            strategy_code = self.propose_strategy()
            
            # 2. Validate it compiles and runs
            strategy = self.load_strategy(strategy_code)
            if not strategy:
                self.log_experiment(i, "INVALID", "Code failed to load")
                continue
            
            # 3. Backtest it
            result = self.backtest(strategy)
            
            # 4. Evaluate vs current best
            if result.metrics.sharpe_ratio and result.metrics.sharpe_ratio > self.best_sharpe:
                self.best_sharpe = result.metrics.sharpe_ratio
                self.best_strategy = strategy
                self.log_experiment(i, "ACCEPTED", f"New best Sharpe: {result.metrics.sharpe_ratio:.2f}")
            else:
                self.log_experiment(i, "REJECTED", f"Sharpe {result.metrics.sharpe_ratio:.2f} < best {self.best_sharpe:.2f}")
```

### 3D. Research Directions File

**`research/directions.md`** (equivalent of Karpathy's `program.md`)

```markdown
# PolyClaw Research Directions

## Priority 1: Exploit known biases
- Favorite-longshot bias: contracts at 5-10% resolve YES only 2-3%
- Overreaction to news: 90% of spikes revert within 24 hours
- Capital lockup aversion: futures markets trade 40% below fair value

## Priority 2: External data sources
- NBA injury reports (official NBA API, beat reporters on X/Twitter)
- Soccer xG data (FBref, Understat)
- Cricket ball-by-ball data (ESPN Cricinfo API)
- Political polling aggregators (FiveThirtyEight, RealClearPolitics)
- Sportsbook odds comparison (Pinnacle, DraftKings via API)

## Priority 3: Market microstructure
- Orderbook imbalance as predictor (bid/ask depth ratio)
- Volume acceleration as momentum signal
- Whale wallet tracking (on-chain activity)
- Cross-platform arbitrage (Polymarket vs Kalshi price divergence)

## Priority 4: Timing patterns
- NBA: best entry 3-5 PM ET on game days
- Elections: enter 50+ days out, prices converge in final 5 days
- Mentions: buy NO pre-event, flip to YES only on confirmed detection
```

### 3E. External Data Integrations

**`src/polyclaw/research/data_sources.py`**

Plug-in architecture for external data:

| Data Source | Category | Signal |
|-------------|----------|--------|
| NBA Injury API | NBA | Load management, rest games → 8% edge on opponent |
| FBref xG | Soccer | Expected goals vs market price divergence |
| ESPN Cricinfo | Cricket | DLS recalculation, toss bias, dot ball % |
| Pinnacle Odds | All Sports | Sportsbook vs Polymarket divergence >5% |
| FiveThirtyEight | Elections | Polling aggregate vs market price divergence |
| Twitter/X API | Mentions | Real-time transcript parsing for keyword detection |

### 3F. CLI + API

```bash
# Run 50 experiments overnight
polyclaw research --experiments 50 --categories NBA,Soccer

# Show leaderboard of tested strategies
polyclaw research --leaderboard

# Run best discovered strategy live
polyclaw research --deploy-best
```

API endpoints:
```
POST /api/research/run         → starts research loop (async)
GET  /api/research/leaderboard → ranked strategies with metrics
GET  /api/research/experiments → full experiment history
POST /api/research/stop        → stop running loop
```

### 3G. Frontend: Research Lab Page

New tab in navigation: **"Research Lab"**
- **Experiment feed**: live log of what the agent is trying (accepted/rejected/invalid)
- **Strategy leaderboard**: table ranked by Sharpe ratio with return %, drawdown, trades
- **Best strategy details**: click to see full backtest results with interactive charts
- **Research directions**: editable markdown of what to explore next
- **Status indicator**: "Running experiment 23/50..." or "Idle"

---

## Implementation Order

| Phase | What | Priority | Effort |
|-------|------|----------|--------|
| 1 | Install recharts, rebuild equity/drawdown/PnL charts with hover interactivity | HIGH | 1 session |
| 2 | Enhanced KPI cards with context bars, comparisons, plain English | HIGH | 1 session |
| 3 | Opportunities: sparklines, edge meter, Kelly stake, risk/reward | HIGH | 1 session |
| 4 | AutoResearch experiment loop + directions.md + CLI | HIGH | 2 sessions |
| 5 | External data source plugins (NBA injury, Pinnacle odds) | MEDIUM | 2 sessions |
| 6 | Strategy comparison mode (overlay equity curves) | MEDIUM | 1 session |
| 7 | Research Lab frontend page (leaderboard, experiment feed) | MEDIUM | 1 session |
| 8 | Trade detail panel + "what if" simulator | LOW | 1 session |

---

## Files to Create

| File | Purpose |
|------|---------|
| `frontend/src/components/InteractiveChart.tsx` | Recharts equity/drawdown/PnL charts |
| `frontend/src/components/EdgeMeter.tsx` | Visual edge bar for opportunities |
| `frontend/src/components/KpiCardEnhanced.tsx` | KPI cards with context |
| `frontend/src/pages/ResearchLabPage.tsx` | Experiment feed + leaderboard |
| `src/polyclaw/research/__init__.py` | Research module |
| `src/polyclaw/research/agent.py` | LLM-powered strategy generator |
| `src/polyclaw/research/experiment_loop.py` | Autoresearch loop |
| `src/polyclaw/research/data_sources.py` | External data plugins |
| `research/directions.md` | Research priorities |

## Files to Modify

| File | Changes |
|------|---------|
| `frontend/src/pages/BacktestPage.tsx` | Replace SVG charts with recharts |
| `frontend/src/pages/OpportunitiesPage.tsx` | Add sparklines, edge meter, Kelly |
| `frontend/src/App.tsx` | Add Research Lab tab |
| `frontend/src/lib/types.ts` | Add research types |
| `frontend/src/App.css` | New component styles |
| `src/polyclaw/web/app.py` | Add /api/research endpoints |
| `src/polyclaw/cli.py` | Add `research` subcommand |
| `frontend/package.json` | Add recharts dependency |

---

## Research Sources

- [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) — 66K+ stars, 630-line experiment loop
- [QuantConnect Backtest Results UI](https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/results) — professional chart layout
- [PolyBackTest](https://polybacktest.com/) — 60M+ orderbook snapshots, AI strategy definition
- [PolySimulator](https://polysimulator.com/backtesting) — no-code rule builder, cross-category testing
- [Verso Terminal](https://polymark.et/product/verso) — Bloomberg-style prediction market terminal
- [Polymarket Trading Strategy Research](./strategy_research.pdf) — 68-source academic analysis
- [Claude's Polymarket Research](./claude_research.pdf) — domain-specific edge analysis
- [VentureBeat: Karpathy's autoresearch](https://venturebeat.com/technology/andrej-karpathys-new-open-source-autoresearch-lets-you-run-hundreds-of-ai) — 700 experiments, 20 improvements
