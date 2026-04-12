from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import urlopen

from .config import FrameworkConfig
from .models import MarketSnapshot, OrderBookSnapshot


class PolymarketPublicClient:
    """
    Thin adapter around public Polymarket API patterns.

    Assumed public structure:
    - Market metadata endpoint (Gamma-style): `/markets`
    - CLOB orderbook endpoint: `/book`
    - CLOB trades endpoint: `/trades`

    Exact field naming can differ by endpoint version. We normalize any
    commonly seen aliases to an internal schema.
    """

    def __init__(self, config: FrameworkConfig):
        self.config = config

    def fetch_markets(self, *, limit: int = 500, closed: bool = False) -> list[dict]:
        query = urlencode({"limit": limit, "closed": str(closed).lower()})
        url = f"{self.config.gamma_base_url}/markets?{query}"
        with urlopen(url, timeout=15) as resp:  # nosec - public GET endpoint
            payload = json.loads(resp.read().decode("utf-8"))
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        if isinstance(payload, list):
            return payload
        return []

    def fetch_order_book(self, token_id: str) -> dict:
        query = urlencode({"token_id": token_id})
        url = f"{self.config.clob_base_url}/book?{query}"
        with urlopen(url, timeout=10) as resp:  # nosec - public GET endpoint
            payload = json.loads(resp.read().decode("utf-8"))
        return payload if isinstance(payload, dict) else {}

    def fetch_recent_trades(self, token_id: str, *, limit: int = 200) -> list[dict]:
        query = urlencode({"token_id": token_id, "limit": limit})
        url = f"{self.config.clob_base_url}/trades?{query}"
        with urlopen(url, timeout=10) as resp:  # nosec - public GET endpoint
            payload = json.loads(resp.read().decode("utf-8"))
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload if isinstance(payload, list) else []

    def normalize_market(self, raw: dict) -> MarketSnapshot:
        market_id = str(raw.get("id") or raw.get("market_id") or raw.get("conditionId"))
        question = str(raw.get("question") or raw.get("title") or raw.get("name") or "")
        category = self._normalize_category(str(raw.get("category") or ""), question, raw)

        event_group = str(
            raw.get("event")
            or raw.get("eventSlug")
            or raw.get("slug")
            or self._event_group_from_question(question)
        )

        end_time = self._parse_datetime(
            raw.get("endDate")
            or raw.get("end_time")
            or raw.get("resolutionDate")
            or raw.get("resolveBy")
        )

        prices = raw.get("prices") or {}
        last_price_yes = self._as_float(
            raw.get("lastPriceYes")
            or raw.get("last_price_yes")
            or prices.get("yes")
            or raw.get("outcomePrices", [None])[0]
        )

        metadata = dict(raw)
        order_book = self._normalize_orderbook(raw.get("orderbook") or raw.get("book") or {})

        return MarketSnapshot(
            market_id=market_id,
            question=question,
            category=category,
            event_group=event_group,
            end_time=end_time,
            volume_24h=self._as_float(raw.get("volume24hr") or raw.get("volume_24h") or 0.0),
            volume_7d=self._as_float(raw.get("volume7d") or raw.get("volume_7d") or 0.0),
            liquidity=self._as_float(raw.get("liquidity") or raw.get("liquidityClob") or 0.0),
            last_price_yes=last_price_yes,
            price_history_yes=self._extract_price_history(raw),
            tags=self._extract_tags(raw),
            metadata=metadata,
            order_book=order_book,
        )

    def normalize_markets(self, rows: list[dict]) -> list[MarketSnapshot]:
        return [self.normalize_market(row) for row in rows]

    @staticmethod
    def _normalize_orderbook(raw: dict) -> OrderBookSnapshot:
        if not isinstance(raw, dict):
            return OrderBookSnapshot()
        return OrderBookSnapshot(
            bid_yes=PolymarketPublicClient._as_float(raw.get("bid_yes") or raw.get("bestBidYes") or raw.get("bid")),
            ask_yes=PolymarketPublicClient._as_float(raw.get("ask_yes") or raw.get("bestAskYes") or raw.get("ask")),
            bid_no=PolymarketPublicClient._as_float(raw.get("bid_no") or raw.get("bestBidNo")),
            ask_no=PolymarketPublicClient._as_float(raw.get("ask_no") or raw.get("bestAskNo")),
            depth_yes=PolymarketPublicClient._as_float(raw.get("depth_yes") or raw.get("depthYes") or 0.0),
            depth_no=PolymarketPublicClient._as_float(raw.get("depth_no") or raw.get("depthNo") or 0.0),
        )

    @staticmethod
    def _extract_price_history(raw: dict) -> list[float]:
        history = raw.get("priceHistoryYes") or raw.get("price_history_yes") or raw.get("prices_yes") or []
        if not isinstance(history, list):
            return []
        output: list[float] = []
        for entry in history:
            if isinstance(entry, dict):
                value = PolymarketPublicClient._as_float(entry.get("price") or entry.get("y"))
            else:
                value = PolymarketPublicClient._as_float(entry)
            if value is not None:
                output.append(value)
        return output

    @staticmethod
    def _extract_tags(raw: dict) -> list[str]:
        source = raw.get("tags") or raw.get("labels") or []
        if not isinstance(source, list):
            return []
        return [str(item).strip() for item in source if str(item).strip()]

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        for candidate in (text, text.replace("Z", "+00:00")):
            try:
                return datetime.fromisoformat(candidate)
            except ValueError:
                continue
        return None

    @staticmethod
    def _event_group_from_question(question: str) -> str:
        words = [w for w in question.lower().split() if w.isalpha()]
        return " ".join(words[:5]) or "unknown-event"

    @staticmethod
    def _as_float(value: object) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_category(category: str, question: str, raw: dict) -> str:
        norm = category.strip().lower()
        question_low = question.lower()

        if norm in {"nba", "basketball"} or "nba" in question_low:
            return "NBA"
        if norm in {"soccer", "football"} or "premier league" in question_low or "uefa" in question_low:
            return "Soccer"
        if norm in {"cricket"} or "ipl" in question_low or "test match" in question_low:
            return "Cricket"
        if norm in {"trump", "donald trump"} or "trump" in question_low:
            return "Trump"
        if norm in {"elections", "election", "politics"} or "election" in question_low:
            return "Elections"

        tags = [str(t).lower() for t in (raw.get("tags") or [])]
        if "trump" in tags:
            return "Trump"
        if "elections" in tags:
            return "Elections"

        return category.strip().title() if category.strip() else "Unknown"

    def debug_dump_market(self, raw: dict) -> dict:
        snap = self.normalize_market(raw)
        payload = asdict(snap)
        payload["end_time"] = snap.end_time.isoformat() if snap.end_time else None
        return payload
