from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import CATEGORIES, FrameworkConfig
from .models import ScoredMarket
from .polymarket_client import PolymarketPublicClient
from .scoring import MarketScorer
from .selection import BetSelector


class SelectionPipeline:
    def __init__(self, config: FrameworkConfig | None = None):
        self.config = config or FrameworkConfig()
        self.client = PolymarketPublicClient(self.config)
        self.scorer = MarketScorer(self.config)
        self.selector = BetSelector(self.config)

    def run_with_public_api(self, *, limit: int = 600) -> dict[str, list[ScoredMarket]]:
        raw_markets = self.client.fetch_markets(limit=limit, closed=False)
        return self.run(raw_markets)

    def run(self, raw_markets: list[dict]) -> dict[str, list[ScoredMarket]]:
        normalized = self.client.normalize_markets(raw_markets)
        filtered = [m for m in normalized if m.category in CATEGORIES]
        scored = [self.scorer.score(m) for m in filtered]
        selected = self.selector.select(scored)

        # Always return each target category with a list.
        return {category: selected.get(category, []) for category in CATEGORIES}

    def run_from_file(self, input_path: str | Path) -> dict[str, list[ScoredMarket]]:
        payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
        rows = payload["markets"] if isinstance(payload, dict) and "markets" in payload else payload
        if not isinstance(rows, list):
            raise ValueError("Input JSON must be a list of market objects or an object with a 'markets' list.")
        return self.run(rows)

    @staticmethod
    def to_output_dict(results: dict[str, list[ScoredMarket]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for category, picks in results.items():
            out[category] = [
                {
                    "market_id": p.market.market_id,
                    "question": p.market.question,
                    "side": p.selected_side,
                    "score": round(p.score, 4),
                    "confidence": round(p.confidence, 4),
                    "p_model_yes": round(p.p_model_yes, 4),
                    "p_market_yes": round(p.p_market_yes, 4),
                    "selected_edge": round(p.selected_edge, 4),
                    "expected_value": round(p.expected_value, 4),
                    "liquidity_score": round(p.features.liquidity_score, 4),
                    "spread_bps": round(p.features.spread_bps, 2),
                    "event_group": p.market.event_group,
                    "rationale_tags": p.rationale_tags,
                }
                for p in picks
            ]
        return out

    @staticmethod
    def write_output(path: str | Path, results: dict[str, list[ScoredMarket]]) -> None:
        serialized = SelectionPipeline.to_output_dict(results)
        Path(path).write_text(json.dumps(serialized, indent=2), encoding="utf-8")
