"""PolyClawClient — typed HTTP client for the /api/v1 surface.

Features:
- Bearer auth injected on every request
- Retry with exponential backoff honoring `Retry-After` headers
- Request ID injection + echo
- Ergonomic wrappers: `place_market_order(token_id, market_id, side, usdc)` instead
  of manually building TradeOrder JSON
- All responses parsed into Pydantic models where possible, raw dicts otherwise
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from polyclaw_sdk.models import (
    BacktestEnqueueResult,
    BacktestRun,
    OrderResult,
    PortfolioSummary,
    Position,
    QuotaInfo,
)


class PolyClawError(RuntimeError):
    """Raised when the API returns a structured error."""

    def __init__(self, code: str, message: str, status: int, details: dict | None = None):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.status = status
        self.details = details or {}


class RiskGateRejected(PolyClawError):
    """Raised on 403 with a risk_gate.* code."""


class QuotaExceeded(PolyClawError):
    """Raised on 429 with a quota.* code."""


@dataclass
class PolyClawClient:
    """Typed HTTP client for the PolyClaw Agent Tools API.

    Args:
        base_url: The platform root (e.g. "http://localhost:5000" or "https://polyclaw.example.com").
        token: Bearer token issued by AgentRegistry.issue_key().
        max_retries: Number of retry attempts on 429/5xx. Default 3.
        timeout: Request timeout in seconds. Default 30.
    """

    base_url: str
    token: str
    max_retries: int = 3
    timeout: float = 30.0
    _http: httpx.Client = field(init=False, repr=False)

    def __post_init__(self):
        self._http = httpx.Client(
            base_url=self.base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ── Core request method with retry ────────────────────────

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        """Execute a request with retry + backoff. Returns parsed JSON body.

        Retries on 429 (honoring Retry-After) and 5xx. Raises PolyClawError
        (or a subclass) on structured error responses.
        """
        request_id = str(uuid.uuid4())
        headers = kwargs.pop("headers", {})
        headers["X-Request-Id"] = request_id

        last_exc: Exception | None = None
        for attempt in range(1 + self.max_retries):
            try:
                resp = self._http.request(method, path, headers=headers, **kwargs)
            except httpx.TransportError as e:
                last_exc = e
                time.sleep(min(2**attempt, 10))
                continue

            if resp.status_code < 400:
                return resp.json()

            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            error = body.get("error", {})
            code = error.get("code", "unknown")
            message = error.get("message", resp.text[:200])
            details = error.get("details")

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 2**attempt))
                if attempt < self.max_retries:
                    time.sleep(min(retry_after, 60))
                    continue
                raise QuotaExceeded(code, message, resp.status_code, details)

            if resp.status_code >= 500 and attempt < self.max_retries:
                time.sleep(min(2**attempt, 10))
                continue

            if resp.status_code == 403 and code.startswith("risk_gate."):
                raise RiskGateRejected(code, message, resp.status_code, details)

            raise PolyClawError(code, message, resp.status_code, details)

        raise last_exc or PolyClawError("max_retries", "Exhausted retries", 0)

    # ── Portfolio reads ───────────────────────────────────────

    def get_portfolio(self) -> PortfolioSummary:
        data = self._request("GET", "/api/v1/portfolio")
        return PortfolioSummary(**data)

    def get_positions(self) -> list[Position]:
        data = self._request("GET", "/api/v1/positions")
        return [Position(**p) for p in data]

    def get_balance(self) -> float:
        data = self._request("GET", "/api/v1/balance")
        return float(data["cash_balance"])

    def get_trades(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/api/v1/trades")
        return data.get("items", [])

    # ── Order placement (ergonomic wrappers) ──────────────────

    def place_order(
        self,
        *,
        token_id: str,
        market_id: str,
        side: str,
        order_type: str = "MARKET",
        size: float,
        price: float | None = None,
        market_question: str = "",
        outcome: str = "",
    ) -> OrderResult:
        """Place an order. Low-level — prefer `place_market_order` or `place_limit_order`."""
        body: dict[str, Any] = {
            "token_id": token_id,
            "market_id": market_id,
            "side": side.upper(),
            "order_type": order_type.upper(),
            "size": size,
            "market_question": market_question,
            "outcome": outcome,
        }
        if price is not None:
            body["price"] = price
        data = self._request("POST", "/api/v1/orders", json=body)
        return OrderResult(**data)

    def place_market_order(
        self,
        token_id: str,
        market_id: str,
        *,
        side: str = "BUY",
        usdc: float,
        outcome: str = "Yes",
    ) -> OrderResult:
        """Place a market order for `usdc` USDC worth of the token."""
        return self.place_order(
            token_id=token_id,
            market_id=market_id,
            side=side,
            order_type="MARKET",
            size=usdc,
            outcome=outcome,
        )

    def place_limit_order(
        self,
        token_id: str,
        market_id: str,
        *,
        side: str = "BUY",
        price: float,
        size: float,
        outcome: str = "Yes",
    ) -> OrderResult:
        """Place a limit order at `price` for `size` shares."""
        return self.place_order(
            token_id=token_id,
            market_id=market_id,
            side=side,
            order_type="LIMIT",
            size=size,
            price=price,
            outcome=outcome,
        )

    def cancel_order(self, order_id: str) -> bool:
        data = self._request("DELETE", f"/api/v1/orders/{order_id}")
        return data.get("ok", False)

    def explain_order(self, order_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/orders/{order_id}/explain")

    # ── Backtest ──────────────────────────────────────────────

    def enqueue_backtest(
        self,
        *,
        strategy: str,
        markets: list[dict[str, Any]],
        params: dict[str, Any] | None = None,
        fidelity: int = 60,
        cash: float = 10_000.0,
    ) -> BacktestEnqueueResult:
        data = self._request(
            "POST",
            "/api/v1/backtest",
            json={
                "strategy": strategy,
                "markets": markets,
                "params": params or {},
                "fidelity": fidelity,
                "cash": cash,
            },
        )
        return BacktestEnqueueResult(**data)

    def get_backtest(self, backtest_id: str) -> BacktestRun:
        data = self._request("GET", f"/api/v1/backtest/{backtest_id}")
        return BacktestRun(**data)

    def wait_for_backtest(self, backtest_id: str, *, timeout_s: float = 120, poll_s: float = 2) -> BacktestRun:
        """Poll until the backtest is terminal (finished/failed) or timeout."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            run = self.get_backtest(backtest_id)
            if run.status in ("finished", "failed"):
                return run
            time.sleep(poll_s)
        raise TimeoutError(f"Backtest {backtest_id} did not finish within {timeout_s}s")

    # ── Leaderboard + quota ───────────────────────────────────

    def get_leaderboard(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/leaderboard")

    def get_quota(self) -> QuotaInfo:
        data = self._request("GET", "/api/v1/quota")
        return QuotaInfo(**data)
