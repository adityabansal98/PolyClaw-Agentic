from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from polyclaw.config import settings
from polyclaw.models.market import Market

logger = logging.getLogger(__name__)

MAX_MARKET_PAGES = 5
MARKET_PAGE_SIZE = 100
OPPORTUNITY_CACHE_TTL = 8
PORTFOLIO_CACHE_TTL = 12
POSITIONS_CACHE_TTL = 12
DETAIL_CACHE_TTL = 8
TOP_LEVEL_DEPTH = 5
DEFAULT_OPPORTUNITY_LIMIT = 36

STRATEGY_OUTPUT_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "live_selection_output_external_required.json"


def _load_strategy_index() -> dict[str, dict[str, Any]]:
    """Load pre-computed strategy scores keyed by market_id."""
    if not STRATEGY_OUTPUT_PATH.exists():
        logger.info("No strategy output file at %s", STRATEGY_OUTPUT_PATH)
        return {}

    try:
        raw = json.loads(STRATEGY_OUTPUT_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to parse strategy output file")
        return {}

    index: dict[str, dict[str, Any]] = {}
    for _category, picks in raw.items():
        if not isinstance(picks, list):
            continue
        for pick in picks:
            market_id = pick.get("market_id")
            if market_id:
                index[str(market_id)] = pick
    return index


NBA_TERMS = {
    "atlanta hawks",
    "boston celtics",
    "brooklyn nets",
    "charlotte hornets",
    "chicago bulls",
    "cleveland cavaliers",
    "dallas mavericks",
    "denver nuggets",
    "detroit pistons",
    "golden state warriors",
    "houston rockets",
    "indiana pacers",
    "los angeles clippers",
    "la clippers",
    "los angeles lakers",
    "la lakers",
    "memphis grizzlies",
    "miami heat",
    "milwaukee bucks",
    "minnesota timberwolves",
    "new orleans pelicans",
    "new york knicks",
    "oklahoma city thunder",
    "orlando magic",
    "philadelphia 76ers",
    "phoenix suns",
    "portland trail blazers",
    "sacramento kings",
    "san antonio spurs",
    "toronto raptors",
    "utah jazz",
    "washington wizards",
    "nba",
    "playoffs",
    "eastern conference",
    "western conference",
}

SOCCER_TERMS = {
    "soccer",
    "football club",
    "premier league",
    "champions league",
    "ucl",
    "europa league",
    "serie a",
    "la liga",
    "bundesliga",
    "ligue 1",
    "mls",
    "fa cup",
    "arsenal",
    "chelsea",
    "liverpool",
    "manchester city",
    "manchester united",
    "tottenham",
    "newcastle",
    "aston villa",
    "west ham",
    "everton",
    "brentford",
    "brighton",
    "fulham",
    "crystal palace",
    "nottingham forest",
    "barcelona",
    "real madrid",
    "atletico madrid",
    "sevilla",
    "valencia",
    "inter",
    "milan",
    "juventus",
    "napoli",
    "roma",
    "lazio",
    "psg",
    "paris saint-germain",
    "bayern",
    "borussia dortmund",
    "ajax",
    "benfica",
    "porto",
    "sporting",
    "celtic",
    "rangers",
}

CRICKET_TERMS = {
    "cricket",
    "ipl",
    "t20",
    "odi",
    "test match",
    "world cup",
    "mumbai indians",
    "chennai super kings",
    "kolkata knight riders",
    "royal challengers",
    "sunrisers",
    "rajasthan royals",
    "delhi capitals",
    "punjab kings",
    "csk",
    "rcb",
    "mi",
}

ELECTION_TERMS = {
    "election",
    "elections",
    "president",
    "presidential",
    "senate",
    "house",
    "governor",
    "primary",
    "democrat",
    "democrats",
    "republican",
    "republicans",
    "electoral college",
    "margin",
    "ballot",
    "popular vote",
    "state result",
    "swing state",
}

MENTION_TERMS = {
    "mention",
    "mentions",
    "speech",
    "say",
    "says",
    "said",
    "words",
    "times",
    "tweet",
    "post",
    "truth social",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: datetime | None = None) -> str:
    stamp = value or utc_now()
    return stamp.isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None

    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def binomial_other_side(price: float | None) -> float | None:
    if price is None:
        return None
    return clamp(1 - price, 0.0, 1.0)


def humanize_duration(target: str | None) -> str:
    when = parse_iso(target)
    if when is None:
        return "Unscheduled"

    hours = (when - utc_now()).total_seconds() / 3600
    if hours < 0:
        return "Resolving"
    if hours < 6:
        return "0-6 hours"
    if hours < 24:
        return "Same day"
    if hours < 72:
        return "1-3 days"
    if hours < 24 * 14:
        return "1-2 weeks"
    return "Longer dated"


def compute_urgency(target: str | None) -> float:
    when = parse_iso(target)
    if when is None:
        return 0.2

    hours = max((when - utc_now()).total_seconds() / 3600, 0)
    if hours <= 6:
        return 0.95
    if hours <= 24:
        return 0.8
    if hours <= 72:
        return 0.65
    if hours <= 24 * 14:
        return 0.45
    return 0.25


def top_book_depth(orderbook) -> float:
    bid_depth = sum(level.price * level.size for level in orderbook.bids[:TOP_LEVEL_DEPTH])
    ask_depth = sum(level.price * level.size for level in orderbook.asks[:TOP_LEVEL_DEPTH])
    return bid_depth + ask_depth


def build_price_history(price: float | None) -> list[float]:
    if price is None:
        return []

    return [
        clamp(price * 0.96, 0.01, 0.99),
        clamp(price * 0.98, 0.01, 0.99),
        price,
    ]


def infer_market_type(market: Market) -> str:
    if market.group_item_title:
        return market.group_item_title
    if market.events:
        title = market.events[0].title.strip()
        if title:
            return title
    return "Binary market"


def market_search_text(market: Market) -> str:
    pieces = [
        market.question,
        market.slug,
        market.description,
        market.group_item_title or "",
        " ".join(event.title for event in market.events),
        " ".join(event.slug for event in market.events),
    ]
    return " ".join(piece for piece in pieces if piece).lower()


def has_any_term(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def classify_market(market: Market) -> str | None:
    text = market_search_text(market)

    if "trump" in text and has_any_term(text, MENTION_TERMS):
        return "Mentions"

    if has_any_term(text, ELECTION_TERMS):
        return "Elections"

    if has_any_term(text, CRICKET_TERMS):
        return "Cricket"

    if has_any_term(text, NBA_TERMS):
        return "NBA"

    if has_any_term(text, SOCCER_TERMS):
        return "Soccer"

    return None


def price_map(market: Market) -> dict[str, float | None]:
    prices: dict[str, float | None] = {}
    for index, outcome in enumerate(market.outcomes):
        prices[outcome.upper()] = to_float(market.outcome_prices[index]) if index < len(market.outcome_prices) else None
    return prices


def token_map(market: Market) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for index, outcome in enumerate(market.outcomes):
        if index < len(market.clob_token_ids):
            tokens[outcome.upper()] = market.clob_token_ids[index]
    return tokens


def pick_primary_outcome(outcomes: list[str]) -> str:
    for preferred in ("YES", "NO"):
        if preferred in (outcome.upper() for outcome in outcomes):
            return preferred
    return outcomes[0].upper() if outcomes else "YES"


def default_ticket_size(liquidity: float, market_depth: float) -> float:
    sizing_anchor = max(min(liquidity * 0.0025, market_depth * 0.3), 100)
    return round(clamp(sizing_anchor, 100, 5000), -2)


def estimated_max_ticket(market_depth: float) -> float:
    return round(clamp(max(market_depth * 0.6, 500), 500, 15000), -2)


@dataclass
class CacheState:
    value: Any = None
    fetched_at: float = 0.0
    latency_ms: int | None = None
    error: str | None = None
    item_count: int = 0

    @property
    def available(self) -> bool:
        return self.value is not None


@dataclass
class DashboardService:
    gamma: Any
    clob: Any
    trader: Any
    opportunities_cache: CacheState = field(default_factory=CacheState)
    portfolio_cache: CacheState = field(default_factory=CacheState)
    positions_cache: CacheState = field(default_factory=CacheState)
    detail_cache: dict[str, CacheState] = field(default_factory=dict)
    market_index: dict[str, Market] = field(default_factory=dict)
    strategy_index: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self):
        self.strategy_index = _load_strategy_index()
        if self.strategy_index:
            logger.info("Loaded %d strategy scores from %s", len(self.strategy_index), STRATEGY_OUTPUT_PATH.name)

    def _strategy_fields(self, market_id: str) -> dict[str, Any]:
        """Return strategy-enriched fields for a given market, falling back to empty defaults."""
        strategy = self.strategy_index.get(str(market_id))
        if not strategy:
            return {
                "recommendedOutcome": None,
                "expectedReturn": None,
                "confidence": None,
                "signalStrength": None,
                "strategyAvailable": False,
                "strategySummary": None,
                "thesis": None,
                "invalidation": None,
                "riskFlags": [
                    "Strategy unavailable",
                    "Human review required before paper execution",
                ],
            }

        side = strategy.get("side")
        ev = strategy.get("expected_value")
        confidence = strategy.get("confidence")
        edge = strategy.get("selected_edge")
        p_model = strategy.get("p_model_yes")
        p_market = strategy.get("p_market_yes")
        p_external = strategy.get("p_external_yes")
        tags = strategy.get("rationale_tags", [])

        thesis_parts = []
        if p_model is not None and p_market is not None:
            thesis_parts.append(f"Model prices YES at {p_model:.1%} vs market {p_market:.1%}.")
        if p_external is not None:
            thesis_parts.append(f"External signals estimate {p_external:.1%}.")
        if edge is not None:
            thesis_parts.append(f"Selected edge: {edge:.1%}.")

        risk_flags = ["Human review required before paper execution"]
        if "relaxed-fill" in tags:
            risk_flags.append("Relaxed fill assumption — check liquidity")
        if edge is not None and edge < 0.05:
            risk_flags.append("Thin edge — monitor closely")

        return {
            "recommendedOutcome": side,
            "expectedReturn": round(ev, 4) if ev is not None else None,
            "confidence": round(confidence, 4) if confidence is not None else None,
            "signalStrength": round(strategy.get("score", 0), 4) or None,
            "strategyAvailable": True,
            "strategySummary": f"{'Buy' if side == 'YES' else 'Sell'} {side} — EV {ev:+.1%}, edge {edge:.1%}" if ev is not None and edge is not None else None,
            "thesis": " ".join(thesis_parts) if thesis_parts else None,
            "invalidation": f"Edge collapses if market moves past model price ({p_model:.1%})" if p_model is not None else None,
            "riskFlags": risk_flags,
        }

    def invalidate_paper_state(self):
        self.portfolio_cache = CacheState()
        self.positions_cache = CacheState()

    def invalidate_market_state(self, market_id: str | None = None):
        if market_id:
            self.detail_cache.pop(market_id, None)
            return
        self.opportunities_cache = CacheState()
        self.detail_cache = {}
        self.market_index = {}

    def _cache_fresh(self, cache: CacheState, ttl_seconds: int) -> bool:
        return cache.available and (time.time() - cache.fetched_at) <= ttl_seconds

    def _serialize_freshness(self, cache: CacheState, stale_after: int, name: str) -> dict[str, Any]:
        if not cache.available:
            return {
                "name": name,
                "available": False,
                "stale": True,
                "updatedAt": None,
                "ageSeconds": None,
                "error": cache.error,
            }

        age_seconds = max(int(time.time() - cache.fetched_at), 0)
        updated_at = datetime.fromtimestamp(cache.fetched_at, tz=timezone.utc)
        return {
            "name": name,
            "available": True,
            "stale": age_seconds > stale_after,
            "updatedAt": isoformat(updated_at),
            "ageSeconds": age_seconds,
            "error": cache.error,
        }

    def _fetch_candidate_markets(self) -> list[Market]:
        markets: list[Market] = []
        for offset in range(0, MAX_MARKET_PAGES * MARKET_PAGE_SIZE, MARKET_PAGE_SIZE):
            page = self.gamma.get_markets(limit=MARKET_PAGE_SIZE, offset=offset)
            markets.extend(page)
            if len(page) < MARKET_PAGE_SIZE:
                break
        return markets

    def _load_opportunities(self) -> list[dict[str, Any]]:
        if self._cache_fresh(self.opportunities_cache, OPPORTUNITY_CACHE_TTL):
            return self.opportunities_cache.value

        started = time.perf_counter()
        markets = self._fetch_candidate_markets()
        categorized: list[Market] = []
        for market in markets:
            if not market.active or market.closed or not market.accepting_orders:
                continue
            if len(market.outcomes) < 2 or len(market.clob_token_ids) < 2:
                continue
            category = classify_market(market)
            if not category:
                continue
            categorized.append(market)

        categorized.sort(key=lambda market: (market.volume_24hr or market.volume or 0, market.liquidity or 0), reverse=True)
        selected = categorized[:DEFAULT_OPPORTUNITY_LIMIT]
        primary_tokens: list[str] = []

        for market in selected:
            tokens = token_map(market)
            primary_outcome = pick_primary_outcome(market.outcomes)
            primary_token = tokens.get(primary_outcome)
            if not primary_token:
                continue
            primary_tokens.append(primary_token)

        orderbooks = self.clob.get_orderbooks_batch(primary_tokens)
        orderbook_map = {orderbook.token_id: orderbook for orderbook in orderbooks}

        items: list[dict[str, Any]] = []
        self.market_index = {}

        for market in selected:
            tokens = token_map(market)
            prices = price_map(market)
            primary_outcome = pick_primary_outcome(market.outcomes)
            primary_token = tokens.get(primary_outcome)
            orderbook = orderbook_map.get(primary_token) if primary_token else None
            if primary_token and not orderbook:
                logger.warning("Skipping %s because the primary orderbook was unavailable", market.id)
                continue

            yes_price = prices.get("YES")
            no_price = prices.get("NO")
            if yes_price is None and orderbook and primary_outcome == "YES":
                yes_price = orderbook.midpoint
            if no_price is None and yes_price is not None:
                no_price = binomial_other_side(yes_price)
            if no_price is None and orderbook and primary_outcome == "NO":
                no_price = orderbook.midpoint
            if yes_price is None and no_price is not None:
                yes_price = binomial_other_side(no_price)

            category = classify_market(market)
            if not category:
                continue

            market_depth = top_book_depth(orderbook) if orderbook else 0.0
            default_stake = default_ticket_size(market.liquidity, market_depth or market.liquidity * 0.02)
            spread_bps = round((orderbook.spread or 0) * 10_000) if orderbook and orderbook.spread is not None else None
            discovered_at = market.created_at or market.start_date or market.end_date or isoformat()
            updated_at = market.updated_at or isoformat()
            tags = [
                category.lower(),
                *(event.title for event in market.events[:2] if event.title),
                market.group_item_title or "",
            ]
            tags = [tag for tag in tags if tag]

            items.append(
                {
                    "id": market.id,
                    "question": market.question,
                    "slug": market.slug,
                    "category": category,
                    "marketType": infer_market_type(market),
                    "statusLabel": "Live market feed",
                    "currentStage": "new",
                    "discoveredAt": discovered_at,
                    "lastUpdatedAt": updated_at,
                    "resolutionDate": market.end_date,
                    "timeHorizon": humanize_duration(market.end_date),
                    "liquidity": market.liquidity,
                    "volume24h": market.volume_24hr or market.volume,
                    "volume": market.volume,
                    "marketDepth": market_depth,
                    "spreadBps": spread_bps,
                    "urgencyScore": compute_urgency(market.end_date),
                    "yesPrice": yes_price,
                    "noPrice": no_price,
                    "bestBid": orderbook.best_bid if orderbook else None,
                    "bestAsk": orderbook.best_ask if orderbook else None,
                    "defaultStake": default_stake,
                    "maxStake": estimated_max_ticket(market_depth or market.liquidity * 0.02),
                    "entryPriceMin": orderbook.best_bid if orderbook else None,
                    "entryPriceMax": orderbook.best_ask if orderbook else None,
                    **self._strategy_fields(market.id),
                    "tags": tags,
                    "tokenIds": tokens,
                    "outcomes": [
                        {
                            "name": outcome,
                            "tokenId": tokens.get(outcome.upper()),
                            "price": prices.get(outcome.upper()),
                        }
                        for outcome in market.outcomes
                    ],
                    "priceHistory": build_price_history(yes_price if yes_price is not None else no_price),
                    "raw": {
                        "groupItemTitle": market.group_item_title,
                        "acceptingOrders": market.accepting_orders,
                        "negRisk": market.neg_risk,
                    },
                }
            )
            self.market_index[market.id] = market

        items.sort(
            key=lambda item: (
                1 if item.get("strategyAvailable") else 0,
                item.get("signalStrength") or 0,
                item.get("volume24h") or 0,
                item.get("liquidity") or 0,
                -(item.get("spreadBps") or 100000),
            ),
            reverse=True,
        )
        self.opportunities_cache = CacheState(
            value=items,
            fetched_at=time.time(),
            latency_ms=round((time.perf_counter() - started) * 1000),
            error=None,
            item_count=len(items),
        )
        return items

    def _load_positions(self) -> list[dict[str, Any]]:
        if self._cache_fresh(self.positions_cache, POSITIONS_CACHE_TTL):
            return self.positions_cache.value

        started = time.perf_counter()
        positions = self.trader.get_positions()
        trade_history = self.trader.get_trade_history()
        opened_lookup: dict[str, int] = {}
        updated_lookup: dict[str, int] = {}
        for trade in trade_history:
            token_id = trade["token_id"]
            opened_lookup[token_id] = min(trade["timestamp"], opened_lookup.get(token_id, trade["timestamp"]))
            updated_lookup[token_id] = max(trade["timestamp"], updated_lookup.get(token_id, trade["timestamp"]))

        items: list[dict[str, Any]] = []
        for position in positions:
            category = classify_market(
                Market(
                    id=position.token_id,
                    question=position.market_question or position.market_id,
                    condition_id=position.market_id,
                    slug=position.market_question.lower().replace(" ", "-") if position.market_question else position.market_id,
                    outcomes=[position.outcome],
                    outcome_prices=[],
                    clob_token_ids=[position.token_id],
                )
            ) or "Uncategorized"
            current_price = position.current_price if position.current_price is not None else position.avg_entry_price
            liquidation_value = position.shares * current_price
            opened_at = opened_lookup.get(position.token_id)
            updated_at = updated_lookup.get(position.token_id)

            items.append(
                {
                    "id": position.token_id,
                    "tokenId": position.token_id,
                    "marketId": position.market_id,
                    "environment": "paper",
                    "question": position.market_question,
                    "category": category,
                    "marketType": "Paper-backed position",
                    "side": "YES" if position.outcome.upper() == "YES" else "NO",
                    "outcome": position.outcome,
                    "shares": position.shares,
                    "stake": position.shares * position.avg_entry_price,
                    "entryPrice": position.avg_entry_price,
                    "currentPrice": current_price,
                    "liquidationValue": liquidation_value,
                    "unrealizedPnl": position.unrealized_pnl or 0.0,
                    "status": "open",
                    "openedAt": isoformat(datetime.fromtimestamp(opened_at / 1000, tz=timezone.utc)) if opened_at else isoformat(),
                    "updatedAt": isoformat(datetime.fromtimestamp(updated_at / 1000, tz=timezone.utc)) if updated_at else isoformat(),
                    "modelView": "Strategy backend is not connected yet. This mark is backed by live market data only.",
                    "thesisAtEntry": "Human-approved paper trade submitted through the dashboard.",
                    "exitGuidance": "Use the paper controls to reduce or close when your thesis changes.",
                    "relatedStrategy": "unavailable",
                    "priceHistory": build_price_history(current_price),
                    "tags": [category.lower(), "paper-book"],
                }
            )

        self.positions_cache = CacheState(
            value=items,
            fetched_at=time.time(),
            latency_ms=round((time.perf_counter() - started) * 1000),
            error=None,
            item_count=len(items),
        )
        return items

    def _load_portfolio(self) -> dict[str, Any]:
        if self._cache_fresh(self.portfolio_cache, PORTFOLIO_CACHE_TTL):
            return self.portfolio_cache.value

        started = time.perf_counter()
        portfolio = self.trader.get_portfolio()
        summary = {
            "environment": "paper",
            "available": True,
            "cashBalance": portfolio.cash_balance,
            "totalPositionValue": portfolio.total_position_value,
            "totalEquity": portfolio.total_equity,
            "totalRealizedPnl": portfolio.total_realized_pnl,
            "totalUnrealizedPnl": portfolio.total_unrealized_pnl,
            "totalReturnImmediate": portfolio.total_equity - settings.paper_starting_balance,
            "openExposure": sum(position.shares * position.avg_entry_price for position in portfolio.positions),
            "availableCapital": portfolio.cash_balance,
            "activePositions": len(portfolio.positions),
            "pendingApprovals": 0,
            "realizedPnl": portfolio.total_realized_pnl,
            "unrealizedPnl": portfolio.total_unrealized_pnl,
            "dailyPnl": 0.0,
            "liquidationValue": portfolio.total_position_value,
        }
        self.portfolio_cache = CacheState(
            value=summary,
            fetched_at=time.time(),
            latency_ms=round((time.perf_counter() - started) * 1000),
            error=None,
            item_count=len(portfolio.positions),
        )
        return summary

    def list_opportunities(self, limit: int | None = None) -> dict[str, Any]:
        try:
            items = self._load_opportunities()
        except Exception as exc:
            logger.exception("Failed to build opportunities")
            self.opportunities_cache.error = str(exc)
            if self.opportunities_cache.available:
                items = self.opportunities_cache.value
            else:
                raise

        limit = limit or DEFAULT_OPPORTUNITY_LIMIT
        freshness = self._serialize_freshness(self.opportunities_cache, OPPORTUNITY_CACHE_TTL * 2, "opportunities")
        return {
            "generatedAt": isoformat(),
            "freshness": freshness,
            "paperExecutionAvailable": True,
            "liveExecutionAvailable": False,
            "items": items[:limit],
            "total": len(items),
        }

    def get_opportunity_detail(self, market_id: str) -> dict[str, Any] | None:
        cache = self.detail_cache.get(market_id)
        if cache and self._cache_fresh(cache, DETAIL_CACHE_TTL):
            return cache.value

        try:
            opportunities = self._load_opportunities()
        except Exception:
            opportunities = self.opportunities_cache.value or []

        summary = next((item for item in opportunities if item["id"] == market_id), None)
        market = self.market_index.get(market_id)
        if not market or not summary:
            try:
                self._load_opportunities()
            except Exception:
                return None
            summary = next((item for item in self.opportunities_cache.value if item["id"] == market_id), None)
            market = self.market_index.get(market_id)
            if not market or not summary:
                return None

        started = time.perf_counter()
        tokens = token_map(market)
        orderbooks = self.clob.get_orderbooks_batch([token for token in tokens.values() if token])
        orderbook_map = {orderbook.token_id: orderbook for orderbook in orderbooks}
        prices = price_map(market)

        outcomes: list[dict[str, Any]] = []
        for outcome in market.outcomes:
            token_id = tokens.get(outcome.upper())
            orderbook = orderbook_map.get(token_id)
            price = prices.get(outcome.upper())
            if price is None and orderbook:
                price = orderbook.midpoint

            outcomes.append(
                {
                    "name": outcome,
                    "tokenId": token_id,
                    "price": price,
                    "bestBid": orderbook.best_bid if orderbook else None,
                    "bestAsk": orderbook.best_ask if orderbook else None,
                    "spreadBps": round((orderbook.spread or 0) * 10_000) if orderbook and orderbook.spread is not None else None,
                    "depth": top_book_depth(orderbook) if orderbook else 0.0,
                    "midpoint": orderbook.midpoint if orderbook else None,
                }
            )

        detail = {
            **summary,
            "description": market.description,
            "eventTitle": market.events[0].title if market.events else None,
            "eventSlug": market.events[0].slug if market.events else None,
            "orderbooksFreshness": {
                "available": True,
                "updatedAt": isoformat(),
            },
            "defaultTokenId": tokens.get("YES") or next(iter(tokens.values()), None),
            "outcomes": outcomes,
        }

        self.detail_cache[market_id] = CacheState(
            value=detail,
            fetched_at=time.time(),
            latency_ms=round((time.perf_counter() - started) * 1000),
            error=None,
            item_count=len(outcomes),
        )
        return detail

    def list_positions(self, environment: str = "paper") -> dict[str, Any]:
        if environment != "paper":
            return {
                "generatedAt": isoformat(),
                "environment": environment,
                "available": False,
                "message": "Live account holdings are not wired yet. Phase 1 only exposes paper-backed positions.",
                "items": [],
            }

        try:
            items = self._load_positions()
        except Exception as exc:
            logger.exception("Failed to build paper positions")
            self.positions_cache.error = str(exc)
            if self.positions_cache.available:
                items = self.positions_cache.value
            else:
                raise

        return {
            "generatedAt": isoformat(),
            "environment": "paper",
            "available": True,
            "freshness": self._serialize_freshness(self.positions_cache, POSITIONS_CACHE_TTL * 2, "positions"),
            "items": items,
        }

    def get_portfolio(self, environment: str = "paper") -> dict[str, Any]:
        if environment != "paper":
            return {
                "generatedAt": isoformat(),
                "environment": environment,
                "available": False,
                "message": "Live account portfolio is not available until Data API integration is implemented.",
                "cash_balance": None,
                "total_position_value": 0.0,
                "total_equity": None,
                "total_realized_pnl": None,
                "total_unrealized_pnl": None,
                "total_return_immediate": None,
                "open_exposure": 0.0,
                "active_positions": 0,
                "liquidation_value": 0.0,
                "positions": [],
            }

        try:
            summary = self._load_portfolio()
        except Exception as exc:
            logger.exception("Failed to build paper portfolio")
            self.portfolio_cache.error = str(exc)
            if self.portfolio_cache.available:
                summary = self.portfolio_cache.value
            else:
                raise

        return {
            "generatedAt": isoformat(),
            "environment": "paper",
            "available": True,
            "freshness": self._serialize_freshness(self.portfolio_cache, PORTFOLIO_CACHE_TTL * 2, "portfolio"),
            "cash_balance": summary["cashBalance"],
            "total_position_value": summary["totalPositionValue"],
            "total_equity": summary["totalEquity"],
            "total_realized_pnl": summary["totalRealizedPnl"],
            "total_unrealized_pnl": summary["totalUnrealizedPnl"],
            "total_return_immediate": summary["totalReturnImmediate"],
            "open_exposure": summary["openExposure"],
            "available_capital": summary["availableCapital"],
            "active_positions": summary["activePositions"],
            "pending_approvals": summary["pendingApprovals"],
            "daily_pnl": summary["dailyPnl"],
            "liquidation_value": summary["liquidationValue"],
            "positions": [
                {
                    "token_id": position["tokenId"],
                    "market_id": position["marketId"],
                    "market_question": position["question"],
                    "outcome": position["outcome"],
                    "shares": position["shares"],
                    "avg_entry_price": position["entryPrice"],
                    "current_price": position["currentPrice"],
                    "unrealized_pnl": position["unrealizedPnl"],
                }
                for position in self._load_positions()
            ],
        }

    def _service_status(self, cache: CacheState, stale_after: int) -> str:
        freshness = self._serialize_freshness(cache, stale_after, "service")
        if not freshness["available"]:
            return "down"
        if freshness["stale"] or freshness["error"]:
            return "degraded"
        return "healthy"

    def build_overview(self) -> dict[str, Any]:
        opportunities = self.list_opportunities()
        paper_positions = self.list_positions("paper")
        paper_summary = self._load_portfolio() if not self.portfolio_cache.available else self.portfolio_cache.value
        if not self.portfolio_cache.available:
            paper_summary = self._load_portfolio()

        services = [
            {
                "id": "gamma-markets",
                "name": "Polymarket market feed",
                "description": "Gamma market metadata transformed into dashboard opportunities.",
                "status": self._service_status(self.opportunities_cache, OPPORTUNITY_CACHE_TTL * 2),
                "latencyMs": self.opportunities_cache.latency_ms or 0,
                "lastHeartbeatAt": self._serialize_freshness(self.opportunities_cache, OPPORTUNITY_CACHE_TTL * 2, "markets")["updatedAt"],
                "owner": "backend",
                "critical": True,
            },
            {
                "id": "paper-book",
                "name": "Paper portfolio",
                "description": "SQLite-backed paper positions and portfolio summary.",
                "status": self._service_status(self.portfolio_cache, PORTFOLIO_CACHE_TTL * 2),
                "latencyMs": self.portfolio_cache.latency_ms or 0,
                "lastHeartbeatAt": self._serialize_freshness(self.portfolio_cache, PORTFOLIO_CACHE_TTL * 2, "portfolio")["updatedAt"],
                "owner": "backend",
                "critical": True,
            },
            {
                "id": "live-execution",
                "name": "Live execution",
                "description": "Disabled in Phase 1 until wallet credentials are configured server-side.",
                "status": "down",
                "latencyMs": 0,
                "lastHeartbeatAt": isoformat(),
                "owner": "backend",
                "critical": False,
            },
        ]

        alerts: list[dict[str, Any]] = [
            {
                "id": "live-holdings-unavailable",
                "tone": "warning",
                "title": "Live account holdings are not connected yet",
                "description": "Overview and Positions are paper-backed in Phase 1 while live market data comes from Polymarket.",
            },
            {
                "id": "strategy-status",
                "tone": "positive" if self.strategy_index else "neutral",
                "title": f"Strategy scoring active — {len(self.strategy_index)} markets scored" if self.strategy_index else "Strategy recommendations are not connected yet",
                "description": (
                    "Opportunities with matched strategies show expected return, confidence, and recommended side."
                    if self.strategy_index
                    else "Opportunities show raw live markets, orderbook depth, and prices. Expected return and confidence stay unavailable for now."
                ),
            },
        ]

        opportunity_count = opportunities["total"]
        if opportunity_count:
            alerts.append(
                {
                    "id": "opportunity-count",
                    "tone": "neutral",
                    "title": f"{opportunity_count} categorized live markets are ready for review",
                    "description": "Use the Opportunities tab to filter by category, inspect the orderbook, and submit paper trades.",
                }
            )

        if opportunities["freshness"]["stale"]:
            alerts.append(
                {
                    "id": "markets-stale",
                    "tone": "critical",
                    "title": "Market data is stale",
                    "description": "Paper execution should pause until the market feed refreshes successfully.",
                }
            )

        overall_status = "healthy"
        if any(service["status"] == "down" and service["critical"] for service in services):
            overall_status = "down"
        elif any(service["status"] != "healthy" for service in services):
            overall_status = "degraded"

        return {
            "generatedAt": isoformat(),
            "lastRefreshAt": isoformat(),
            "backendHealthSummary": {
                "status": overall_status,
                "paperExecutionAvailable": True,
                "liveExecutionAvailable": False,
                "liveHoldingsAvailable": False,
            },
            "dataFreshness": {
                "opportunities": self._serialize_freshness(self.opportunities_cache, OPPORTUNITY_CACHE_TTL * 2, "opportunities"),
                "portfolio": self._serialize_freshness(self.portfolio_cache, PORTFOLIO_CACHE_TTL * 2, "portfolio"),
                "positions": self._serialize_freshness(self.positions_cache, POSITIONS_CACHE_TTL * 2, "positions"),
            },
            "paperSummary": paper_summary,
            "liveSummary": {
                "environment": "live",
                "available": False,
                "totalReturnImmediate": None,
                "openExposure": 0.0,
                "availableCapital": None,
                "activePositions": 0,
                "pendingApprovals": 0,
                "realizedPnl": None,
                "unrealizedPnl": None,
                "dailyPnl": None,
                "liquidationValue": 0.0,
            },
            "paperPositionsCount": len(paper_positions["items"]),
            "pendingOpportunityCount": opportunity_count,
            "alerts": alerts,
            "services": services,
        }
