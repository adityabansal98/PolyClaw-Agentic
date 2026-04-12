# PolyClaw

Framework for selecting top Polymarket bets across:
- NBA
- Soccer
- Cricket
- Trump
- Elections

It also includes ingestion, trading, and a web dashboard served through FastAPI.

The current implementation builds a reusable pipeline to:
1. Normalize Polymarket public-market JSON payloads.
2. Engineer market microstructure features.
3. Estimate fair probability (`p_model`) per market.
4. Compute edge and expected value for YES/NO sides.
5. Apply risk/diversification constraints.
6. Return top 5 picks per category.

## Structure

- `polyclaw/config.py`: framework config, category list, risk constraints.
- `polyclaw/models.py`: internal dataclasses.
- `polyclaw/polymarket_client.py`: public-API assumptions + normalization layer.
- `polyclaw/features.py`: feature engineering.
- `polyclaw/scoring.py`: fair probability + EV + confidence + final scoring.
- `polyclaw/selection.py`: constrained top-N selector.
- `polyclaw/pipeline.py`: end-to-end orchestration.
- `run_selector.py`: CLI entry point.
- `data/sample_markets.json`: sample payload for local smoke tests.

## Public API Assumptions

The client assumes a common documented split:
- Market metadata API (`gamma` style): `GET /markets`
- CLOB API (`execution` style): `GET /book`, `GET /trades`

Field names may differ by endpoint/version. The normalizer maps common aliases into one internal schema.

## Quick Start

```bash
python3 run_selector.py --input data/sample_markets.json --output data/selection_output.json --pretty
```

This writes output to `data/selection_output.json` with the selected side, score, confidence, edge, EV, and rationale tags.

## Dashboard

The React dashboard source lives in `frontend/`. The Python web app serves the compiled output from
`src/polyclaw/web/static/app`.

Build the frontend:

```bash
cd frontend
npm install
npm run build
```

Run the web server:

```bash
polyclaw web --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000/`.

For frontend-only development:

```bash
cd frontend
npm run dev
```

## Output Shape

```json
{
  "NBA": [
    {
      "market_id": "nba-1",
      "question": "...",
      "side": "YES",
      "score": 0.73,
      "confidence": 0.78,
      "p_model_yes": 0.64,
      "p_market_yes": 0.61,
      "selected_edge": 0.03,
      "expected_value": 0.03,
      "liquidity_score": 0.67,
      "spread_bps": 200.0,
      "event_group": "...",
      "rationale_tags": ["strong-edge", "positive-ev"]
    }
  ]
}
```

## Notes for Next Step (Strategy Planner)

This framework intentionally separates signal generation from execution sizing, so a later strategy planner can consume output and apply:
- stake sizing (Kelly/vol-targeted),
- inventory and risk budgets,
- execution tactics (limit laddering, slippage controls),
- portfolio-level hedging rules.
