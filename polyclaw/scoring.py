from __future__ import annotations

from .config import FrameworkConfig
from .features import build_feature_vector, clamp
from .models import MarketSnapshot, ScoredMarket


class MarketScorer:
    def __init__(self, config: FrameworkConfig):
        self.config = config

    def score(self, market: MarketSnapshot) -> ScoredMarket:
        f = build_feature_vector(market)
        p_market = f.market_probability_yes

        p_model = self._fair_probability(market, f)
        confidence = self._confidence(market, f)

        ask_yes = market.order_book.ask_yes if market.order_book.ask_yes is not None else p_market
        bid_yes = market.order_book.bid_yes if market.order_book.bid_yes is not None else p_market

        # Simple EV approximation with entry at current ask/bid and payout 1.0 at resolution.
        ev_yes = p_model * (1.0 - ask_yes) - (1.0 - p_model) * ask_yes

        # For NO, convert via complementary probability and implied NO entry price.
        ask_no = market.order_book.ask_no
        no_price = ask_no if ask_no is not None else (1.0 - bid_yes)
        p_no = 1.0 - p_model
        ev_no = p_no * (1.0 - no_price) - (1.0 - p_no) * no_price

        edge_yes = p_model - p_market
        edge_no = (1.0 - p_model) - (1.0 - p_market)

        if ev_yes >= ev_no:
            selected_side = "YES"
            selected_edge = edge_yes
            expected_value = ev_yes
        else:
            selected_side = "NO"
            selected_edge = edge_no
            expected_value = ev_no

        weights = self.config.base_weights
        cat_multiplier = self.config.category_weight_multipliers.get(market.category, 1.0)

        score = cat_multiplier * (
            weights.edge * clamp(selected_edge + 0.5, 0.0, 1.0)
            + weights.confidence * confidence
            + weights.liquidity * f.liquidity_score
            + weights.execution * f.execution_score
            + weights.momentum * clamp(0.5 + 0.5 * f.momentum_7d, 0.0, 1.0)
        )

        rationale = self._rationale_tags(market, f, selected_edge, confidence, expected_value)

        return ScoredMarket(
            market=market,
            features=f,
            p_model_yes=p_model,
            p_market_yes=p_market,
            edge_yes=edge_yes,
            edge_no=edge_no,
            expected_value_yes=ev_yes,
            expected_value_no=ev_no,
            selected_side=selected_side,
            selected_edge=selected_edge,
            expected_value=expected_value,
            confidence=confidence,
            correlation_key=self._correlation_key(market),
            score=score,
            rationale_tags=rationale,
        )

    def _fair_probability(self, market: MarketSnapshot, f) -> float:
        # Baseline from market price, then nudge with market microstructure and category priors.
        p = f.market_probability_yes

        micro_adj = (
            0.16 * f.momentum_7d
            + 0.10 * f.momentum_1d
            + 0.09 * f.order_imbalance
            + 0.07 * clamp(f.volume_acceleration, -1.0, 1.0)
            - 0.06 * f.volatility
            + 0.04 * f.time_decay
        )

        category_adj = self._category_adjustment(market, f)
        p_model = clamp(p + micro_adj + category_adj, 0.01, 0.99)
        return p_model

    def _confidence(self, market: MarketSnapshot, f) -> float:
        data_quality = 0.0
        data_quality += 0.20 if market.last_price_yes is not None else 0.0
        data_quality += 0.20 if market.order_book.bid_yes is not None else 0.0
        data_quality += 0.20 if market.order_book.ask_yes is not None else 0.0
        data_quality += 0.20 if len(market.price_history_yes) >= 5 else 0.0
        data_quality += 0.20 if market.volume_24h > 0 else 0.0

        confidence = (
            0.45 * f.liquidity_score
            + 0.20 * f.execution_score
            + 0.15 * (1.0 - clamp(f.spread_bps / 700.0, 0.0, 1.0))
            + 0.20 * data_quality
        )
        return clamp(confidence, 0.0, 1.0)

    def _category_adjustment(self, market: MarketSnapshot, f) -> float:
        q = market.question.lower()
        tags = {t.lower() for t in market.tags}

        if market.category == "NBA":
            injury_like = any(k in q for k in ("injury", "questionable", "out"))
            playoff_like = any(k in q for k in ("playoff", "finals", "series"))
            return (0.025 if playoff_like else 0.0) - (0.020 if injury_like else 0.0)

        if market.category == "Soccer":
            derby_like = any(k in q for k in ("derby", "champions league", "uefa"))
            low_total_like = any(k in q for k in ("under 2.5", "clean sheet"))
            return (0.020 if derby_like else 0.0) + (0.010 if low_total_like and f.volatility < 0.08 else 0.0)

        if market.category == "Cricket":
            toss_like = any(k in q for k in ("toss", "powerplay"))
            ipl_like = "ipl" in q or "ipl" in tags
            return (0.015 if ipl_like else 0.0) - (0.020 if toss_like else 0.0)

        if market.category == "Trump":
            legal_headline_like = any(k in q for k in ("indict", "verdict", "court"))
            return (0.020 if "poll" in q else 0.0) - (0.020 if legal_headline_like else 0.0)

        if market.category == "Elections":
            swing_state_like = any(k in q for k in ("pennsylvania", "michigan", "wisconsin", "arizona", "georgia"))
            turnout_like = any(k in q for k in ("turnout", "mail-in", "early voting"))
            return (0.025 if swing_state_like else 0.0) + (0.010 if turnout_like else 0.0)

        return 0.0

    @staticmethod
    def _correlation_key(market: MarketSnapshot) -> set[str]:
        base_tokens = {
            token.lower()
            for token in market.question.replace("?", " ").replace("/", " ").split()
            if len(token) >= 4
        }
        return base_tokens | {market.event_group.lower()} | {market.category.lower()}

    @staticmethod
    def _rationale_tags(
        market: MarketSnapshot,
        f,
        selected_edge: float,
        confidence: float,
        ev: float,
    ) -> list[str]:
        tags: list[str] = [market.category.lower()]
        if selected_edge > 0.03:
            tags.append("strong-edge")
        if confidence > 0.72:
            tags.append("high-confidence")
        if f.liquidity_score > 0.55:
            tags.append("good-liquidity")
        if f.spread_bps < 180:
            tags.append("tight-spread")
        if ev > 0.02:
            tags.append("positive-ev")
        return tags
