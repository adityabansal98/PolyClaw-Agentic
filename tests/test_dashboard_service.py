from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from polyclaw.models.market import Market
from polyclaw.models.orderbook import OrderBook, OrderLevel
from polyclaw.trading.models import PortfolioSummary, Position
from polyclaw.web.app import app as flask_app
from polyclaw.web.dashboard_service import DashboardService


def make_market(
    *,
    market_id: str,
    question: str,
    slug: str,
    group_item_title: str,
    outcomes: list[str] | None = None,
    outcome_prices: list[str] | None = None,
    token_ids: list[str] | None = None,
) -> Market:
    return Market(
        id=market_id,
        question=question,
        condition_id=f"condition-{market_id}",
        slug=slug,
        group_item_title=group_item_title,
        outcomes=outcomes or ["Yes", "No"],
        outcome_prices=outcome_prices or ["0.58", "0.42"],
        clob_token_ids=token_ids or [f"{market_id}-yes", f"{market_id}-no"],
        active=True,
        closed=False,
        accepting_orders=True,
        liquidity=250000,
        volume=150000,
        volume_24hr=72000,
        end_date="2026-05-01T12:00:00Z",
        created_at="2026-04-12T12:00:00Z",
        updated_at="2026-04-12T12:05:00Z",
    )


def make_orderbook(token_id: str, market_id: str) -> OrderBook:
    return OrderBook(
        token_id=token_id,
        market_id=market_id,
        bids=[OrderLevel(price=0.57, size=1500), OrderLevel(price=0.56, size=1000)],
        asks=[OrderLevel(price=0.59, size=1200), OrderLevel(price=0.60, size=900)],
        spread=0.02,
        midpoint=0.58,
        best_bid=0.57,
        best_ask=0.59,
        timestamp=1712923200000,
    )


class FakeGamma:
    def __init__(self, markets: list[Market]):
        self.markets = markets
        self.fail = False

    def get_markets(self, limit: int = 100, offset: int = 0):
        if self.fail:
            raise RuntimeError("gamma unavailable")
        return self.markets[offset : offset + limit]


class FakeClob:
    def __init__(self, orderbooks: dict[str, OrderBook]):
        self.orderbooks = orderbooks

    def get_orderbooks_batch(self, token_ids: list[str]):
        return [self.orderbooks[token_id] for token_id in token_ids if token_id in self.orderbooks]

    def get_orderbook(self, token_id: str):
        return self.orderbooks[token_id]


class FakeTrader:
    def __init__(self):
        self.positions = [
            Position(
                token_id="nba-yes-token",
                market_id="market-nba",
                market_question="Will the Knicks win tonight?",
                outcome="YES",
                shares=100,
                avg_entry_price=0.55,
                current_price=0.60,
                unrealized_pnl=5.0,
            )
        ]
        self.portfolio = PortfolioSummary(
            cash_balance=9500,
            positions=self.positions,
            total_position_value=60.0,
            total_equity=9560.0,
            total_realized_pnl=10.0,
            total_unrealized_pnl=5.0,
        )

    def get_positions(self):
        return self.positions

    def get_portfolio(self):
        return self.portfolio

    def get_trade_history(self):
        return [
            {
                "token_id": "nba-yes-token",
                "timestamp": 1712916000000,
            },
            {
                "token_id": "nba-yes-token",
                "timestamp": 1712919600000,
            },
        ]


@pytest.fixture
def dashboard_service():
    nba_market = make_market(
        market_id="market-nba",
        question="Will the Knicks win tonight?",
        slug="knicks-win-tonight",
        group_item_title="NBA moneyline",
        token_ids=["nba-yes-token", "nba-no-token"],
    )
    uncategorized_market = make_market(
        market_id="market-uncat",
        question="Will it rain tomorrow in Seattle?",
        slug="rain-seattle",
        group_item_title="Weather",
        token_ids=["weather-yes-token", "weather-no-token"],
    )

    gamma = FakeGamma([nba_market, uncategorized_market])
    clob = FakeClob(
        {
            "nba-yes-token": make_orderbook("nba-yes-token", "market-nba"),
            "nba-no-token": make_orderbook("nba-no-token", "market-nba"),
            "weather-yes-token": make_orderbook("weather-yes-token", "market-uncat"),
        }
    )
    trader = FakeTrader()
    return DashboardService(gamma=gamma, clob=clob, trader=trader)


def test_list_opportunities_transforms_markets_into_dashboard_rows(dashboard_service: DashboardService):
    payload = dashboard_service.list_opportunities()

    assert payload["total"] == 1
    opportunity = payload["items"][0]
    assert opportunity["question"] == "Will the Knicks win tonight?"
    assert opportunity["category"] == "NBA"
    assert opportunity["yesPrice"] == pytest.approx(0.58)
    assert opportunity["noPrice"] == pytest.approx(0.42)
    assert opportunity["strategyAvailable"] is False
    assert opportunity["spreadBps"] == 200


def test_opportunity_detail_returns_outcome_and_orderbook_linkage(dashboard_service: DashboardService):
    dashboard_service.list_opportunities()

    detail = dashboard_service.get_opportunity_detail("market-nba")

    assert detail is not None
    assert detail["defaultTokenId"] == "nba-yes-token"
    assert len(detail["outcomes"]) == 2
    yes_outcome = next(outcome for outcome in detail["outcomes"] if outcome["name"] == "Yes")
    assert yes_outcome["tokenId"] == "nba-yes-token"
    assert yes_outcome["bestBid"] == pytest.approx(0.57)


def test_overview_exposes_paper_summary_health_and_capabilities(dashboard_service: DashboardService):
    dashboard_service.list_opportunities()
    dashboard_service.list_positions("paper")
    dashboard_service.get_portfolio("paper")

    overview = dashboard_service.build_overview()

    assert overview["backendHealthSummary"]["paperExecutionAvailable"] is True
    assert overview["backendHealthSummary"]["liveExecutionAvailable"] is False
    assert overview["paperSummary"]["available"] is True
    assert overview["paperSummary"]["activePositions"] == 1
    assert overview["pendingOpportunityCount"] == 1


def test_opportunities_fall_back_to_cached_data_if_gamma_fails_after_first_sync(dashboard_service: DashboardService):
    first_payload = dashboard_service.list_opportunities()
    dashboard_service.gamma.fail = True

    second_payload = dashboard_service.list_opportunities()

    assert second_payload["total"] == first_payload["total"]
    assert second_payload["items"][0]["question"] == first_payload["items"][0]["question"]


def test_opportunities_endpoint_uses_dashboard_service(monkeypatch, dashboard_service: DashboardService):
    monkeypatch.setattr("polyclaw.web.app.get_dashboard_service", lambda: dashboard_service)

    client = flask_app.test_client()
    response = client.get("/api/opportunities")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total"] == 1
    assert payload["items"][0]["category"] == "NBA"


def test_positions_endpoint_reports_live_holdings_unavailable(monkeypatch, dashboard_service: DashboardService):
    monkeypatch.setattr("polyclaw.web.app.get_dashboard_service", lambda: dashboard_service)

    client = flask_app.test_client()
    response = client.get("/api/positions?environment=live")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["available"] is False
    assert payload["items"] == []
    assert "Phase 1" in payload["message"]
