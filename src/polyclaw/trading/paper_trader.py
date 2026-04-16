"""Multi-tenant paper trading engine — Phase 1.

Rewritten from the Phase 0 single-tenant implementation. Changes from Phase 0:

- `agent_id` is a required constructor parameter; every query scopes by it.
- `Clock` and `MarketDataProvider` are injected — no `time.time()` or `clob.get_orderbook()`
  calls anywhere in the trading path. Production uses `SystemClock` + `LiveMarketDataProvider`;
  replay tests use `VirtualClock` + `ReplayMarketDataProvider`.
- Fill math uses `decimal.Decimal` at the boundary. Floats are not associative across
  platforms, so "byte-identical replay" isn't achievable with float arithmetic. Decimal
  is the only honest way to make the §10 success criterion hold.
- SQLAlchemy Core replaces the two parallel SQLite + PostgREST code paths. One code path
  works against both dialects.
- Cash debits go through `SELECT ... FOR UPDATE` on Postgres / `BEGIN IMMEDIATE` on SQLite
  so two threads debiting the same agent's cash can't lose writes.
- Every `place_order` that results in a fill writes a row to `audit_log` + links the
  `orderbook_snapshots` row that drove the fill, transactionally with the trade row.
- A `PortfolioSampler` helper records `portfolio_snapshots` on every trade and (in prod)
  every 60s via an in-process sampler. The Phase 2c worker will take over the 60s cadence
  in production; the in-process path stays for dev.

Out of scope (Phase 2+):
- `TradingService` + `RiskGate` wrapper
- `AgentRegistry` integration (agents are still identified by bare string ids)
- Postgres `price_ticks` source (the `audit_log.price_tick_id` column is reserved but nullable)
"""

from __future__ import annotations

import json
import logging
import uuid
from decimal import ROUND_HALF_EVEN, Decimal, getcontext
from typing import Any

from sqlalchemy import Engine, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from polyclaw.storage.db import (
    AgentNotInitialized,
    begin_exclusive,
    ensure_agent_row,
    ensure_schema,
    is_postgres,
    make_engine,
)
from polyclaw.storage.schema import (
    DASHBOARD_AGENT_ID,
    audit_log,
    orderbook_snapshots,
    paper_config,
    paper_open_orders,
    paper_positions,
    paper_trades,
    portfolio_snapshots,
)
from polyclaw.trading.clock import Clock, SystemClock
from polyclaw.trading.interface import TraderInterface
from polyclaw.trading.market_data import (
    LiveMarketDataProvider,
    MarketDataProvider,
    orderbook_content_hash,
    orderbook_to_json,
)
from polyclaw.trading.models import (
    OrderResult,
    OrderStatus,
    PortfolioSummary,
    Position,
    Side,
    TradeOrder,
    TradeOrderType,
)

logger = logging.getLogger(__name__)

# Decimal precision wide enough to handle (size * price * fee_rate) without losing bits.
# 28 is Python's default; we bump to 40 to be safe against pathological multi-level fills.
getcontext().prec = 40
_Q_USDC = Decimal("0.00000001")  # 8-dp quantization for serialized cash amounts


def _d(x: float | int | str | Decimal) -> Decimal:
    """Convert to Decimal via string to avoid float→Decimal bit-noise."""
    return x if isinstance(x, Decimal) else Decimal(str(x))


def _q(x: Decimal) -> float:
    """Quantize a Decimal to 8dp and return as float for JSON / DB serialization."""
    return float(x.quantize(_Q_USDC, rounding=ROUND_HALF_EVEN))


# ── Provenance hashing ─────────────────────────────────────────────────────


def _hash_request(order: TradeOrder) -> str:
    import hashlib

    payload = json.dumps(
        {
            "token_id": order.token_id,
            "market_id": order.market_id,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "price": order.price,
            "size": order.size,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _hash_response(result: OrderResult) -> str:
    import hashlib

    payload = json.dumps(
        {
            "status": result.status.value,
            "filled_price": result.filled_price,
            "filled_size": result.filled_size,
            "total_cost": result.total_cost,
            "message": result.message,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


# ── PaperTrader ────────────────────────────────────────────────────────────


class PaperTrader(TraderInterface):
    """Multi-tenant paper trader. One instance per agent + process; safe to share the
    underlying `Engine` across instances."""

    def __init__(
        self,
        *,
        agent_id: str,
        engine: Engine,
        clock: Clock | None = None,
        market_data: MarketDataProvider | None = None,
        starting_balance: float = 10_000.0,
        season_id: str | None = None,
    ):
        if not agent_id:
            raise ValueError("PaperTrader requires a non-empty agent_id")
        self.agent_id = agent_id
        self.engine = engine
        self.clock: Clock = clock or SystemClock()
        self.market_data: MarketDataProvider = market_data or LiveMarketDataProvider()
        self.season_id = season_id

        ensure_schema(engine)
        ensure_agent_row(engine, agent_id, starting_balance)

        # Fee rate cache is per-instance; the underlying CLOB client lives inside
        # `market_data` if the provider is live.
        self._fee_bps_cache: dict[str, int] = {}

        logger.info("PaperTrader initialized for agent_id=%s on %s", agent_id, engine.url.drivername)

    # ── Cash helpers ────────────────────────────────────────────

    def _get_cash(self, conn: Any) -> Decimal:
        row = conn.execute(
            select(paper_config.c.value)
            .where(paper_config.c.agent_id == self.agent_id)
            .where(paper_config.c.key == "cash_balance")
        ).first()
        if row is None:
            raise AgentNotInitialized(
                f"No paper_config row for agent_id={self.agent_id!r}. "
                "Create the agent via AgentRegistry (or PaperTrader's starting_balance "
                "seeding path) before trading."
            )
        return _d(row[0])

    def _get_cash_for_update(self, conn: Any) -> Decimal:
        """Lock the cash row for update (Postgres only; SQLite is covered by BEGIN IMMEDIATE)."""
        if is_postgres(conn):
            row = conn.execute(
                text(
                    "SELECT value FROM paper_config WHERE agent_id = :a AND key = 'cash_balance' FOR UPDATE"
                ),
                {"a": self.agent_id},
            ).first()
            if row is None:
                raise AgentNotInitialized(f"No paper_config row for agent_id={self.agent_id!r}")
            return _d(row[0])
        return self._get_cash(conn)

    def _set_cash(self, conn: Any, amount: Decimal) -> None:
        conn.execute(
            update(paper_config)
            .where(paper_config.c.agent_id == self.agent_id)
            .where(paper_config.c.key == "cash_balance")
            .values(value=str(_q(amount)))
        )

    def _get_fee_rate(self, token_id: str) -> Decimal:
        if token_id in self._fee_bps_cache:
            return _d(self._fee_bps_cache[token_id]) / _d(10_000)
        bps = 0
        # Only the live provider knows how to fetch fee rates. Replay tests should
        # use a fee_rate that's set on the provider or left at 0.
        live = getattr(self.market_data, "_clob", None)
        if live is not None:
            try:
                bps = live._client.get_fee_rate_bps(token_id)
            except Exception:
                logger.warning("Failed to fetch fee rate for %s, defaulting to 0", token_id[:20])
        self._fee_bps_cache[token_id] = int(bps)
        return _d(bps) / _d(10_000)

    def _get_held_shares(self, conn: Any, token_id: str) -> Decimal:
        row = conn.execute(
            select(paper_positions.c.shares)
            .where(paper_positions.c.agent_id == self.agent_id)
            .where(paper_positions.c.token_id == token_id)
        ).first()
        return _d(row[0]) if row else _d(0)

    # ── Audit + snapshot writes ─────────────────────────────────

    def _persist_orderbook_snapshot(
        self, conn: Any, book_json: str, content_hash: str, token_id: str, ts_ms: int
    ) -> int:
        """Insert an orderbook snapshot, deduping on content_hash. Returns the row id."""
        # Try fast path: find existing row by hash.
        existing = conn.execute(
            select(orderbook_snapshots.c.id).where(orderbook_snapshots.c.content_hash == content_hash)
        ).first()
        if existing is not None:
            return int(existing[0])

        insert_fn = pg_insert if is_postgres(conn) else sqlite_insert
        stmt = insert_fn(orderbook_snapshots).values(
            token_id=token_id,
            ts_ms=ts_ms,
            snapshot_json=book_json,
            content_hash=content_hash,
        )
        # On conflict (concurrent writer raced us), fetch the existing row.
        stmt = stmt.on_conflict_do_nothing(index_elements=["content_hash"])
        result = conn.execute(stmt)
        inserted_pk = result.inserted_primary_key
        if inserted_pk is not None and inserted_pk[0] is not None:
            return int(inserted_pk[0])
        # Lost the race — look up the winning row.
        row = conn.execute(
            select(orderbook_snapshots.c.id).where(orderbook_snapshots.c.content_hash == content_hash)
        ).first()
        assert row is not None
        return int(row[0])

    def _write_audit(
        self,
        conn: Any,
        *,
        endpoint: str,
        request_hash: str,
        response_hash: str,
        orderbook_snapshot_id: int | None,
        request_id: str,
    ) -> None:
        conn.execute(
            audit_log.insert().values(
                agent_id=self.agent_id,
                ts_ms=self.clock.now_ms(),
                endpoint=endpoint,
                request_hash=request_hash,
                response_hash=response_hash,
                orderbook_snapshot_id=orderbook_snapshot_id,
                price_tick_id=None,  # Phase 2a
                season_id=self.season_id,
                request_id=request_id,
            )
        )

    # ── Order execution ─────────────────────────────────────────

    def place_order(self, order: TradeOrder, *, request_id: str | None = None) -> OrderResult:
        request_id = request_id or str(uuid.uuid4())
        if order.order_type == TradeOrderType.MARKET:
            return self._execute_market_order(order, request_id=request_id)
        return self._execute_limit_order(order, request_id=request_id)

    def _execute_market_order(self, order: TradeOrder, *, request_id: str) -> OrderResult:
        trade_id = str(uuid.uuid4())[:12]
        as_of = self.clock.now_ms()

        # 1) Fetch the orderbook via the provider (NOT direct CLOB). This is the
        #    critical replay fix — live mode pass-through, replay mode reads a
        #    frozen snapshot.
        try:
            book = self.market_data.get_orderbook(order.token_id, as_of_ts=as_of)
        except Exception as e:
            result = OrderResult(
                order_id=trade_id,
                status=OrderStatus.REJECTED,
                message=f"Failed to fetch orderbook: {e}",
            )
            return result

        # 2) Compute the fill against the frozen book (Decimal math, no DB yet).
        plan = self._plan_market_fill(order, book, as_of)
        if plan["status"] == OrderStatus.REJECTED:
            return OrderResult(
                order_id=trade_id,
                status=OrderStatus.REJECTED,
                message=plan["message"],
            )

        # 3) Persist: cash, position, trade, audit, snapshot — all in one tx.
        with self.engine.connect() as conn, begin_exclusive(conn):
            cash = self._get_cash_for_update(conn)
            total_cost: Decimal = plan["total_cost"]
            total_shares: Decimal = plan["total_shares"]
            fee: Decimal = plan["fee"]
            avg_price: Decimal = plan["avg_price"]

            if order.side == Side.BUY:
                if cash < total_cost + fee:
                    # Rare: liquidity shifted between plan and lock. Reject honestly.
                    return OrderResult(
                        order_id=trade_id,
                        status=OrderStatus.REJECTED,
                        message="Insufficient cash at execution time",
                    )
                new_cash = cash - total_cost - fee
            else:
                held = self._get_held_shares(conn, order.token_id)
                if held < total_shares:
                    return OrderResult(
                        order_id=trade_id,
                        status=OrderStatus.REJECTED,
                        message=f"Insufficient shares held ({float(held)} < {float(total_shares)})",
                    )
                new_cash = cash + total_cost - fee

            self._set_cash(conn, new_cash)
            self._update_position(conn, order, total_shares, avg_price)

            snapshot_id = self._persist_orderbook_snapshot(
                conn,
                book_json=plan["book_json"],
                content_hash=plan["book_hash"],
                token_id=order.token_id,
                ts_ms=as_of,
            )

            conn.execute(
                paper_trades.insert().values(
                    id=trade_id,
                    agent_id=self.agent_id,
                    token_id=order.token_id,
                    market_id=order.market_id,
                    market_question=order.market_question,
                    outcome=order.outcome,
                    side=order.side.value,
                    order_type=order.order_type.value,
                    requested_price=order.price,
                    filled_price=_q(avg_price),
                    filled_size=_q(total_shares),
                    total_cost=_q(total_cost),
                    fee=_q(fee),
                    status=OrderStatus.FILLED.value,
                    timestamp=as_of,
                )
            )

            result = OrderResult(
                order_id=trade_id,
                status=OrderStatus.FILLED,
                filled_price=_q(avg_price),
                filled_size=_q(total_shares),
                total_cost=_q(total_cost),
            )

            self._write_audit(
                conn,
                endpoint="orders.place_market",
                request_hash=_hash_request(order),
                response_hash=_hash_response(result),
                orderbook_snapshot_id=snapshot_id,
                request_id=request_id,
            )

            self._snapshot_portfolio(conn, ts_ms=as_of)

        logger.info(
            "PAPER %s %s %s: %.4f shares @ %.4f (cost %.2f, fee %.2f) [%s]",
            self.agent_id,
            order.side.value,
            order.outcome,
            float(total_shares),
            float(avg_price),
            float(total_cost),
            float(fee),
            trade_id,
        )
        return result

    def _plan_market_fill(self, order: TradeOrder, book, as_of_ts: int) -> dict:
        """Walk the orderbook and compute the fill in Decimal, without touching the DB."""
        if order.side == Side.BUY:
            levels = sorted(book.asks, key=lambda lv: lv.price)
        else:
            levels = sorted(book.bids, key=lambda lv: lv.price, reverse=True)

        if not levels:
            return {
                "status": OrderStatus.REJECTED,
                "message": f"No {'asks' if order.side == Side.BUY else 'bids'} in orderbook",
            }

        remaining = _d(order.size)
        total_cost = _d(0)
        total_shares = _d(0)

        # For BUY, `size` is USDC; for SELL, `size` is shares. Matches the TradeOrder docstring.
        for level in levels:
            if remaining <= 0:
                break
            lvl_price = _d(level.price)
            lvl_size = _d(level.size)
            if order.side == Side.BUY:
                usdc_at_level = lvl_size * lvl_price
                usdc_to_fill = min(remaining, usdc_at_level)
                shares_filled = usdc_to_fill / lvl_price
                total_cost += usdc_to_fill
                total_shares += shares_filled
                remaining -= usdc_to_fill
            else:
                shares_at_level = min(remaining, lvl_size)
                usdc_received = shares_at_level * lvl_price
                total_cost += usdc_received
                total_shares += shares_at_level
                remaining -= shares_at_level

        if total_shares == 0:
            return {"status": OrderStatus.REJECTED, "message": "Insufficient liquidity in orderbook"}

        avg_price = total_cost / total_shares
        fee_rate = self._get_fee_rate(order.token_id)
        fee = total_cost * fee_rate

        return {
            "status": OrderStatus.FILLED,
            "total_cost": total_cost,
            "total_shares": total_shares,
            "avg_price": avg_price,
            "fee": fee,
            "book_json": orderbook_to_json(book),
            "book_hash": orderbook_content_hash(book),
        }

    def _execute_limit_order(self, order: TradeOrder, *, request_id: str) -> OrderResult:
        trade_id = str(uuid.uuid4())[:12]
        as_of = self.clock.now_ms()

        if order.price is None:
            return OrderResult(
                order_id=trade_id,
                status=OrderStatus.REJECTED,
                message="Limit orders require a price.",
            )

        try:
            book = self.market_data.get_orderbook(order.token_id, as_of_ts=as_of)
        except Exception as e:
            return OrderResult(
                order_id=trade_id,
                status=OrderStatus.REJECTED,
                message=f"Failed to fetch orderbook: {e}",
            )

        if order.side == Side.BUY:
            fillable = sorted([lv for lv in book.asks if lv.price <= order.price], key=lambda lv: lv.price)
        else:
            fillable = sorted(
                [lv for lv in book.bids if lv.price >= order.price], key=lambda lv: lv.price, reverse=True
            )

        if not fillable:
            # Resting limit order → paper_open_orders.
            with self.engine.connect() as conn, begin_exclusive(conn):
                conn.execute(
                    paper_open_orders.insert().values(
                        id=trade_id,
                        agent_id=self.agent_id,
                        token_id=order.token_id,
                        market_id=order.market_id,
                        market_question=order.market_question,
                        outcome=order.outcome,
                        side=order.side.value,
                        price=order.price,
                        size=order.size,
                        filled_size=0,
                        timestamp=as_of,
                    )
                )
                result = OrderResult(
                    order_id=trade_id,
                    status=OrderStatus.PENDING,
                    message="Limit order placed (not yet fillable)",
                )
                self._write_audit(
                    conn,
                    endpoint="orders.place_limit_pending",
                    request_hash=_hash_request(order),
                    response_hash=_hash_response(result),
                    orderbook_snapshot_id=None,
                    request_id=request_id,
                )
            return result

        # Fillable → walk the book (Decimal)
        remaining = _d(order.size)
        total_cost = _d(0)
        total_shares = _d(0)
        for level in fillable:
            if remaining <= 0:
                break
            fill = min(remaining, _d(level.size))
            total_cost += fill * _d(level.price)
            total_shares += fill
            remaining -= fill

        if total_shares == 0:
            return OrderResult(
                order_id=trade_id, status=OrderStatus.REJECTED, message="Insufficient liquidity"
            )

        avg_price = total_cost / total_shares
        fee_rate = self._get_fee_rate(order.token_id)
        fee = total_cost * fee_rate

        with self.engine.connect() as conn, begin_exclusive(conn):
            cash = self._get_cash_for_update(conn)
            if order.side == Side.BUY:
                if cash < total_cost + fee:
                    return OrderResult(
                        order_id=trade_id,
                        status=OrderStatus.REJECTED,
                        message="Insufficient cash at execution time",
                    )
                new_cash = cash - total_cost - fee
            else:
                held = self._get_held_shares(conn, order.token_id)
                if held < total_shares:
                    return OrderResult(
                        order_id=trade_id,
                        status=OrderStatus.REJECTED,
                        message="Insufficient shares held",
                    )
                new_cash = cash + total_cost - fee

            self._set_cash(conn, new_cash)
            self._update_position(conn, order, total_shares, avg_price)

            snapshot_id = self._persist_orderbook_snapshot(
                conn,
                book_json=orderbook_to_json(book),
                content_hash=orderbook_content_hash(book),
                token_id=order.token_id,
                ts_ms=as_of,
            )

            status = OrderStatus.FILLED if remaining <= 0 else OrderStatus.PARTIALLY_FILLED
            conn.execute(
                paper_trades.insert().values(
                    id=trade_id,
                    agent_id=self.agent_id,
                    token_id=order.token_id,
                    market_id=order.market_id,
                    market_question=order.market_question,
                    outcome=order.outcome,
                    side=order.side.value,
                    order_type=order.order_type.value,
                    requested_price=order.price,
                    filled_price=_q(avg_price),
                    filled_size=_q(total_shares),
                    total_cost=_q(total_cost),
                    fee=_q(fee),
                    status=status.value,
                    timestamp=as_of,
                )
            )
            result = OrderResult(
                order_id=trade_id,
                status=status,
                filled_price=_q(avg_price),
                filled_size=_q(total_shares),
                total_cost=_q(total_cost),
            )
            self._write_audit(
                conn,
                endpoint="orders.place_limit",
                request_hash=_hash_request(order),
                response_hash=_hash_response(result),
                orderbook_snapshot_id=snapshot_id,
                request_id=request_id,
            )
            self._snapshot_portfolio(conn, ts_ms=as_of)

        return result

    # ── Position updates ────────────────────────────────────────

    def _update_position(self, conn: Any, order: TradeOrder, shares: Decimal, price: Decimal) -> None:
        row = conn.execute(
            select(
                paper_positions.c.shares,
                paper_positions.c.avg_entry_price,
                paper_positions.c.realized_pnl,
            )
            .where(paper_positions.c.agent_id == self.agent_id)
            .where(paper_positions.c.token_id == order.token_id)
        ).first()

        if order.side == Side.BUY:
            if row is None:
                conn.execute(
                    paper_positions.insert().values(
                        agent_id=self.agent_id,
                        token_id=order.token_id,
                        market_id=order.market_id,
                        market_question=order.market_question,
                        outcome=order.outcome,
                        shares=_q(shares),
                        avg_entry_price=_q(price),
                        realized_pnl=0.0,
                    )
                )
            else:
                old_shares = _d(row[0])
                old_avg = _d(row[1])
                new_shares = old_shares + shares
                new_avg = (
                    ((old_shares * old_avg) + (shares * price)) / new_shares if new_shares > 0 else _d(0)
                )
                conn.execute(
                    update(paper_positions)
                    .where(paper_positions.c.agent_id == self.agent_id)
                    .where(paper_positions.c.token_id == order.token_id)
                    .values(shares=_q(new_shares), avg_entry_price=_q(new_avg))
                )
        else:
            if row is None or _d(row[0]) <= 0:
                return
            old_shares = _d(row[0])
            old_avg = _d(row[1])
            old_realized = _d(row[2])
            sell_shares = min(shares, old_shares)
            realized = sell_shares * (price - old_avg)
            new_shares = old_shares - sell_shares
            new_realized = old_realized + realized
            conn.execute(
                update(paper_positions)
                .where(paper_positions.c.agent_id == self.agent_id)
                .where(paper_positions.c.token_id == order.token_id)
                .values(
                    shares=_q(new_shares if new_shares > Decimal("0.001") else _d(0)),
                    realized_pnl=_q(new_realized),
                )
            )

    # ── Portfolio sampler ───────────────────────────────────────

    def _snapshot_portfolio(self, conn: Any, *, ts_ms: int) -> None:
        """Write a portfolio_snapshots row at the current transaction. Called on every trade
        and (in prod) every 60s by the sampler loop."""
        cash = self._get_cash(conn)
        rows = conn.execute(
            select(
                paper_positions.c.shares, paper_positions.c.avg_entry_price, paper_positions.c.realized_pnl
            ).where(paper_positions.c.agent_id == self.agent_id)
        ).fetchall()
        position_value = _d(0)
        realized = _d(0)
        for r in rows:
            position_value += _d(r[0]) * _d(r[1])  # marked at entry; true marks come later
            realized += _d(r[2])
        conn.execute(
            portfolio_snapshots.insert().values(
                agent_id=self.agent_id,
                ts_ms=ts_ms,
                cash=_q(cash),
                position_value=_q(position_value),
                total_equity=_q(cash + position_value),
                realized_pnl=_q(realized),
                unrealized_pnl=0.0,
            )
        )

    def sample_portfolio(self) -> None:
        """Public entry point for the 60s sampler loop. Wraps in its own transaction."""
        with self.engine.begin() as conn:
            self._snapshot_portfolio(conn, ts_ms=self.clock.now_ms())

    # ── Read API ────────────────────────────────────────────────

    def cancel_order(self, order_id: str) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(
                paper_open_orders.delete()
                .where(paper_open_orders.c.agent_id == self.agent_id)
                .where(paper_open_orders.c.id == order_id)
            )
            return (result.rowcount or 0) > 0

    def get_positions(self) -> list[Position]:
        with self.engine.connect() as conn:
            rows = (
                conn.execute(
                    select(paper_positions)
                    .where(paper_positions.c.agent_id == self.agent_id)
                    .where(paper_positions.c.shares > 0.001)
                )
                .mappings()
                .all()
            )
        out: list[Position] = []
        for r in rows:
            current_price = None
            unrealized = 0.0
            # Mark-to-market via live provider if available; tests use 0.
            live = getattr(self.market_data, "_clob", None)
            if live is not None:
                try:
                    snap = live.get_price(r["token_id"], market_id=r["market_id"])
                    current_price = snap.midpoint
                    if current_price is not None:
                        unrealized = float(r["shares"]) * (current_price - float(r["avg_entry_price"]))
                except Exception:
                    pass
            out.append(
                Position(
                    token_id=r["token_id"],
                    market_id=r["market_id"],
                    market_question=r["market_question"],
                    outcome=r["outcome"],
                    shares=float(r["shares"]),
                    avg_entry_price=float(r["avg_entry_price"]),
                    current_price=current_price,
                    unrealized_pnl=unrealized,
                )
            )
        return out

    def get_portfolio(self) -> PortfolioSummary:
        with self.engine.connect() as conn:
            cash = float(self._get_cash(conn))
            realized_row = conn.execute(
                text("SELECT COALESCE(SUM(realized_pnl), 0) FROM paper_positions WHERE agent_id = :a"),
                {"a": self.agent_id},
            ).first()
            total_realized = float(realized_row[0]) if realized_row else 0.0
        positions = self.get_positions()
        total_position_value = sum(p.shares * (p.current_price or p.avg_entry_price) for p in positions)
        total_unrealized = sum(p.unrealized_pnl or 0.0 for p in positions)
        return PortfolioSummary(
            cash_balance=cash,
            positions=positions,
            total_position_value=total_position_value,
            total_equity=cash + total_position_value,
            total_realized_pnl=total_realized,
            total_unrealized_pnl=total_unrealized,
        )

    def get_balance(self) -> float:
        with self.engine.connect() as conn:
            return float(self._get_cash(conn))

    def get_trade_history(self) -> list[dict]:
        with self.engine.connect() as conn:
            rows = (
                conn.execute(
                    select(paper_trades)
                    .where(paper_trades.c.agent_id == self.agent_id)
                    .order_by(paper_trades.c.timestamp.desc())
                )
                .mappings()
                .all()
            )
            return [dict(r) for r in rows]

    def check_open_orders(self) -> None:
        """Re-check resting limit orders and attempt to fill any that are now executable."""
        with self.engine.connect() as conn:
            rows = (
                conn.execute(select(paper_open_orders).where(paper_open_orders.c.agent_id == self.agent_id))
                .mappings()
                .all()
            )

        for r in rows:
            order = TradeOrder(
                token_id=r["token_id"],
                market_id=r["market_id"],
                market_question=r["market_question"],
                outcome=r["outcome"],
                side=Side(r["side"]),
                order_type=TradeOrderType.LIMIT,
                price=float(r["price"]),
                size=float(r["size"]) - float(r["filled_size"]),
            )
            result = self._execute_limit_order(order, request_id=str(uuid.uuid4()))
            if result.status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED):
                with self.engine.begin() as conn:
                    conn.execute(
                        paper_open_orders.delete()
                        .where(paper_open_orders.c.id == r["id"])
                        .where(paper_open_orders.c.agent_id == self.agent_id)
                    )

    def reset(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(paper_trades.delete().where(paper_trades.c.agent_id == self.agent_id))
            conn.execute(paper_positions.delete().where(paper_positions.c.agent_id == self.agent_id))
            conn.execute(paper_open_orders.delete().where(paper_open_orders.c.agent_id == self.agent_id))
            starting = conn.execute(
                select(paper_config.c.value)
                .where(paper_config.c.agent_id == self.agent_id)
                .where(paper_config.c.key == "starting_balance")
            ).first()
            balance = _d(starting[0]) if starting else _d(10_000)
            self._set_cash(conn, balance)
        self._fee_bps_cache.clear()

    def close(self) -> None:
        # Engine lifetime is managed by the caller (usually the process).
        pass


# ── Dashboard entry point (Phase 2b: returns a TradingService) ────────────


def make_dashboard_service(
    db_path: str = "paper_trading.db",
    starting_balance: float = 10_000.0,
    clob=None,
):
    """Build a `TradingService` wired to the dashboard's `__dashboard__` agent.

    Phase 2b makes `TradingService` the single chokepoint for all order writes, so
    the dashboard no longer holds a raw PaperTrader. Instead it holds a
    TradingService and calls methods like `svc.get_portfolio(DASHBOARD_AGENT_ID)`.
    The agent row is seeded up front via `AgentRegistry.create_agent` so the paper_config
    balance is authoritative.
    """
    import os

    from polyclaw.agents.registry import AgentRegistry, AgentTier
    from polyclaw.config import settings
    from polyclaw.trading.service import TradingService

    settings.enforce_production_guard()
    database_url = getattr(settings, "database_url", "") or os.environ.get("POLYCLAW_DATABASE_URL", "")
    if settings.db_backend == "supabase" or database_url:
        url = database_url
        if not url:
            raise RuntimeError(
                "db_backend=supabase requires POLYCLAW_DATABASE_URL (postgresql+psycopg://...) to be set."
            )
    else:
        # On Vercel (serverless), CWD is read-only; /tmp is the only writable path.
        if os.environ.get("VERCEL"):
            db_path = f"/tmp/{db_path}"
        url = f"sqlite:///{db_path}"

    engine = make_engine(url)
    market_data = LiveMarketDataProvider(clob=clob) if clob is not None else LiveMarketDataProvider()
    registry = AgentRegistry(engine)
    registry.create_agent(
        DASHBOARD_AGENT_ID,
        name="Dashboard",
        starting_balance=starting_balance,
        tier=AgentTier.HOSTED_INPROCESS,
    )
    return TradingService(engine=engine, market_data=market_data)


def make_dashboard_trader(
    db_path: str = "paper_trading.db",
    starting_balance: float = 10_000.0,
    clob=None,
) -> PaperTrader:
    """Back-compat for tests + CLI paper-reset. Returns a bare PaperTrader bound to
    the dashboard agent. Production call sites should use `make_dashboard_service`."""
    import os

    from polyclaw.agents.registry import AgentRegistry, AgentTier
    from polyclaw.config import settings

    settings.enforce_production_guard()
    database_url = getattr(settings, "database_url", "") or os.environ.get("POLYCLAW_DATABASE_URL", "")
    if settings.db_backend == "supabase" or database_url:
        url = database_url
        if not url:
            raise RuntimeError(
                "db_backend=supabase requires POLYCLAW_DATABASE_URL (postgresql+psycopg://...) to be set."
            )
    else:
        if os.environ.get("VERCEL"):
            db_path = f"/tmp/{db_path}"
        url = f"sqlite:///{db_path}"

    engine = make_engine(url)
    market_data = LiveMarketDataProvider(clob=clob) if clob is not None else LiveMarketDataProvider()
    registry = AgentRegistry(engine)
    registry.create_agent(
        DASHBOARD_AGENT_ID,
        name="Dashboard",
        starting_balance=starting_balance,
        tier=AgentTier.HOSTED_INPROCESS,
    )
    return PaperTrader(
        agent_id=DASHBOARD_AGENT_ID,
        engine=engine,
        starting_balance=starting_balance,
        market_data=market_data,
    )
