"""Pydantic models for SDK responses. Mirrors the server-side shapes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Position(BaseModel):
    token_id: str
    market_id: str
    market_question: str = ""
    outcome: str = ""
    shares: float
    avg_entry_price: float
    current_price: float | None = None
    unrealized_pnl: float | None = None


class PortfolioSummary(BaseModel):
    cash_balance: float
    positions: list[Position] = []
    total_position_value: float = 0.0
    total_equity: float = 0.0
    total_realized_pnl: float = 0.0
    total_unrealized_pnl: float = 0.0


class OrderResult(BaseModel):
    order_id: str
    status: str
    filled_price: float | None = None
    filled_size: float | None = None
    total_cost: float | None = None
    message: str = ""


class BacktestEnqueueResult(BaseModel):
    backtest_id: str
    status: str


class BacktestRun(BaseModel):
    id: str
    agent_id: str
    strategy: str
    status: str
    enqueued_at_ms: int
    started_at_ms: int | None = None
    finished_at_ms: int | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class QuotaInfo(BaseModel):
    agent_id: str
    tier: str
    trading: dict[str, float] = {}
    backtest: dict[str, Any] = {}
