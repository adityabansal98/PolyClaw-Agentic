from __future__ import annotations

from collections import defaultdict

from .config import FrameworkConfig
from .models import ScoredMarket


class BetSelector:
    def __init__(self, config: FrameworkConfig):
        self.config = config

    def select(self, scored_markets: list[ScoredMarket]) -> dict[str, list[ScoredMarket]]:
        by_cat: dict[str, list[ScoredMarket]] = defaultdict(list)
        for m in scored_markets:
            by_cat[m.market.category].append(m)

        result: dict[str, list[ScoredMarket]] = {}
        for category, candidates in by_cat.items():
            result[category] = self._select_for_category(candidates)
        return result

    def _select_for_category(self, candidates: list[ScoredMarket]) -> list[ScoredMarket]:
        c = self.config.constraints

        valid = [
            m
            for m in candidates
            if m.confidence >= c.min_confidence
            and m.selected_edge >= c.min_edge
            and m.features.liquidity_score >= c.min_liquidity_score
            and m.features.spread_bps <= c.max_spread_bps
            and m.expected_value > 0.0
        ]

        valid.sort(key=lambda m: m.score, reverse=True)

        selected: list[ScoredMarket] = []
        event_group_counts: dict[str, int] = defaultdict(int)

        for candidate in valid:
            if len(selected) >= c.picks_per_category:
                break

            event_group = candidate.market.event_group.lower()
            if event_group_counts[event_group] >= c.max_per_event_group:
                continue

            if self._too_correlated(candidate, selected, c.max_pairwise_correlation):
                continue

            selected.append(candidate)
            event_group_counts[event_group] += 1

        # If constraints are too strict, backfill by score while still requiring positive EV.
        if len(selected) < c.picks_per_category:
            selected_ids = {m.market.market_id for m in selected}
            for candidate in sorted(candidates, key=lambda m: m.score, reverse=True):
                if len(selected) >= c.picks_per_category:
                    break
                if candidate.market.market_id in selected_ids:
                    continue
                if candidate.expected_value <= 0:
                    continue
                selected.append(candidate)
                selected_ids.add(candidate.market.market_id)

        return selected

    @staticmethod
    def _too_correlated(
        candidate: ScoredMarket,
        selected: list[ScoredMarket],
        max_pairwise_correlation: float,
    ) -> bool:
        for item in selected:
            corr = _jaccard_similarity(candidate.correlation_key, item.correlation_key)
            if corr >= max_pairwise_correlation:
                return True
        return False


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))
