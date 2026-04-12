import json
import logging
import sqlite3
import time
import uuid

from polyclaw.clients.clob import ClobClientWrapper
from polyclaw.trading.interface import TraderInterface
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

PAPER_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_config (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS paper_trades (
    id TEXT PRIMARY KEY,
    token_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    market_question TEXT DEFAULT '',
    outcome TEXT DEFAULT '',
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    requested_price REAL,
    filled_price REAL,
    filled_size REAL,
    total_cost REAL,
    fee REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    timestamp INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_positions (
    token_id TEXT PRIMARY KEY,
    market_id TEXT NOT NULL,
    market_question TEXT DEFAULT '',
    outcome TEXT DEFAULT '',
    shares REAL NOT NULL DEFAULT 0,
    avg_entry_price REAL NOT NULL DEFAULT 0,
    realized_pnl REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS paper_open_orders (
    id TEXT PRIMARY KEY,
    token_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    market_question TEXT DEFAULT '',
    outcome TEXT DEFAULT '',
    side TEXT NOT NULL,
    price REAL NOT NULL,
    size REAL NOT NULL,
    filled_size REAL NOT NULL DEFAULT 0,
    timestamp INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_paper_trades_token ON paper_trades(token_id);
CREATE INDEX IF NOT EXISTS idx_paper_trades_ts ON paper_trades(timestamp);
"""


class PaperTrader(TraderInterface):
    """Simulated trading engine that uses real Polymarket orderbook data.

    - Tracks positions, cash balance, and PnL in a local SQLite database.
    - Market orders fill at the real best bid/ask from the live orderbook.
    - Limit orders fill if the orderbook price crosses your limit price.
    - Simulates slippage by walking the orderbook for large orders.
    - Deducts Polymarket fees (fetched per-market via CLOB API).
    - Starting balance is configurable (default $10,000 USDC).
    """

    def __init__(
        self,
        db_path: str = "paper_trading.db",
        starting_balance: float = 10_000.0,
        clob: ClobClientWrapper | None = None,
    ):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(PAPER_SCHEMA)

        # Add fee column if upgrading from old schema
        try:
            self.conn.execute("ALTER TABLE paper_trades ADD COLUMN fee REAL NOT NULL DEFAULT 0")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

        self.clob = clob or ClobClientWrapper()
        self._fee_cache: dict[str, int] = {}

        # Initialize balance if first run
        row = self.conn.execute(
            "SELECT value FROM paper_config WHERE key = 'cash_balance'"
        ).fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO paper_config (key, value) VALUES ('cash_balance', ?)",
                (str(starting_balance),),
            )
            self.conn.execute(
                "INSERT INTO paper_config (key, value) VALUES ('starting_balance', ?)",
                (str(starting_balance),),
            )
            self.conn.commit()
            logger.info("Paper trading initialized with $%.2f", starting_balance)

    def _get_cash(self) -> float:
        row = self.conn.execute(
            "SELECT value FROM paper_config WHERE key = 'cash_balance'"
        ).fetchone()
        return float(row["value"])

    def _set_cash(self, amount: float):
        self.conn.execute(
            "UPDATE paper_config SET value = ? WHERE key = 'cash_balance'",
            (str(amount),),
        )

    def _get_fee_rate(self, token_id: str) -> float:
        """Get fee rate as a decimal (e.g. 0.02 for 200bps) from CLOB API, cached."""
        if token_id in self._fee_cache:
            return self._fee_cache[token_id] / 10_000

        try:
            bps = self.clob._client.get_fee_rate_bps(token_id)
        except Exception:
            bps = 0
            logger.warning("Failed to fetch fee rate for %s, defaulting to 0", token_id[:30])

        self._fee_cache[token_id] = bps
        return bps / 10_000

    def place_order(self, order: TradeOrder) -> OrderResult:
        if order.order_type == TradeOrderType.MARKET:
            return self._execute_market_order(order)
        else:
            return self._execute_limit_order(order)

    def _execute_market_order(self, order: TradeOrder) -> OrderResult:
        """Fill a market order against the live orderbook with slippage simulation."""
        trade_id = str(uuid.uuid4())[:12]

        try:
            ob = self.clob.get_orderbook(order.token_id)
        except Exception as e:
            return OrderResult(
                order_id=trade_id,
                status=OrderStatus.REJECTED,
                message=f"Failed to fetch orderbook: {e}",
            )

        # For BUY: walk the asks (ascending price). For SELL: walk the bids (descending price).
        if order.side == Side.BUY:
            levels = sorted(ob.asks, key=lambda l: l.price)  # cheapest first
        else:
            levels = sorted(ob.bids, key=lambda l: l.price, reverse=True)  # most expensive first

        if not levels:
            return OrderResult(
                order_id=trade_id,
                status=OrderStatus.REJECTED,
                message=f"No {'asks' if order.side == Side.BUY else 'bids'} in orderbook",
            )

        # FIX #5: Check cash upfront for buys, check shares for sells
        cash = self._get_cash()

        if order.side == Side.SELL:
            # FIX #2: Reject if insufficient shares
            held = self._get_held_shares(order.token_id)
            if held <= 0:
                return OrderResult(
                    order_id=trade_id,
                    status=OrderStatus.REJECTED,
                    message=f"No shares held to sell",
                )
            # Cap sell size to held shares
            effective_size = min(order.size, held)
        else:
            effective_size = order.size

        # Walk the book to simulate fill with slippage
        remaining = effective_size
        total_cost = 0.0
        total_shares = 0.0

        for level in levels:
            if remaining <= 0:
                break

            if order.side == Side.BUY:
                # size is USDC amount for market buys
                # FIX #5: Stop early if out of cash
                cash_left = cash - total_cost
                if cash_left <= 0:
                    break
                usdc_at_level = level.size * level.price
                usdc_to_fill = min(remaining, usdc_at_level, cash_left)
                shares_filled = usdc_to_fill / level.price
                total_cost += usdc_to_fill
                total_shares += shares_filled
                remaining -= usdc_to_fill
            else:
                # size is shares for sells
                shares_at_level = min(remaining, level.size)
                usdc_received = shares_at_level * level.price
                total_cost += usdc_received
                total_shares += shares_at_level
                remaining -= shares_at_level

        if total_shares == 0:
            return OrderResult(
                order_id=trade_id,
                status=OrderStatus.REJECTED,
                message="Insufficient liquidity in orderbook",
            )

        avg_price = total_cost / total_shares if total_shares > 0 else 0

        # FIX #1: Calculate and deduct Polymarket fees
        fee_rate = self._get_fee_rate(order.token_id)
        fee = total_cost * fee_rate

        # Execute the fill
        if order.side == Side.BUY:
            self._set_cash(cash - total_cost - fee)
            self._update_position(order, total_shares, avg_price)
        else:
            self._set_cash(cash + total_cost - fee)
            self._update_position(order, total_shares, avg_price)

        # Record the trade
        now = int(time.time() * 1000)
        self.conn.execute(
            """INSERT INTO paper_trades
               (id, token_id, market_id, market_question, outcome, side,
                order_type, requested_price, filled_price, filled_size,
                total_cost, fee, status, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (trade_id, order.token_id, order.market_id, order.market_question,
             order.outcome, order.side.value, order.order_type.value,
             order.price, avg_price, total_shares, total_cost, fee,
             OrderStatus.FILLED.value, now),
        )
        self.conn.commit()

        fee_str = f" (fee ${fee:.2f})" if fee > 0 else ""
        logger.info(
            "PAPER %s %s: %.2f shares @ avg $%.4f (cost $%.2f%s) | %s [%s]",
            order.side.value, order.outcome, total_shares, avg_price,
            total_cost, fee_str, order.market_question[:40], trade_id,
        )

        return OrderResult(
            order_id=trade_id,
            status=OrderStatus.FILLED,
            filled_price=avg_price,
            filled_size=total_shares,
            total_cost=total_cost,
        )

    def _execute_limit_order(self, order: TradeOrder) -> OrderResult:
        """Check if a limit order can fill against the live orderbook."""
        trade_id = str(uuid.uuid4())[:12]

        if order.price is None:
            return OrderResult(
                order_id=trade_id,
                status=OrderStatus.REJECTED,
                message="Limit orders require a price.",
            )

        try:
            ob = self.clob.get_orderbook(order.token_id)
        except Exception as e:
            return OrderResult(
                order_id=trade_id,
                status=OrderStatus.REJECTED,
                message=f"Failed to fetch orderbook: {e}",
            )

        # Check if limit price crosses the book
        if order.side == Side.BUY:
            fillable_levels = [a for a in ob.asks if a.price <= order.price]
            fillable_levels.sort(key=lambda l: l.price)
        else:
            fillable_levels = [b for b in ob.bids if b.price >= order.price]
            fillable_levels.sort(key=lambda l: l.price, reverse=True)

        if not fillable_levels:
            # Store as open order for later checking
            now = int(time.time() * 1000)
            self.conn.execute(
                """INSERT INTO paper_open_orders
                   (id, token_id, market_id, market_question, outcome,
                    side, price, size, filled_size, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
                (trade_id, order.token_id, order.market_id,
                 order.market_question, order.outcome,
                 order.side.value, order.price, order.size, now),
            )
            self.conn.commit()

            logger.info(
                "PAPER LIMIT %s %s: %.0f shares @ $%.4f (pending) | %s [%s]",
                order.side.value, order.outcome, order.size,
                order.price, order.market_question[:40], trade_id,
            )
            return OrderResult(
                order_id=trade_id,
                status=OrderStatus.PENDING,
                message="Limit order placed (not yet fillable at current prices)",
            )

        # FIX #2: For sells, cap to held shares
        effective_size = order.size
        if order.side == Side.SELL:
            held = self._get_held_shares(order.token_id)
            if held <= 0:
                return OrderResult(
                    order_id=trade_id,
                    status=OrderStatus.REJECTED,
                    message="No shares held to sell",
                )
            effective_size = min(order.size, held)

        # Walk fillable levels
        cash = self._get_cash()
        remaining = effective_size
        total_cost = 0.0
        total_shares = 0.0

        for level in fillable_levels:
            if remaining <= 0:
                break

            fill = min(remaining, level.size)

            # FIX #5: For buys, check cash per level
            if order.side == Side.BUY:
                level_cost = fill * level.price
                cash_left = cash - total_cost
                if level_cost > cash_left:
                    fill = cash_left / level.price
                    if fill <= 0:
                        break

            total_cost += fill * level.price
            total_shares += fill
            remaining -= fill

        if total_shares == 0:
            return OrderResult(
                order_id=trade_id,
                status=OrderStatus.REJECTED,
                message="Insufficient funds or liquidity",
            )

        avg_price = total_cost / total_shares if total_shares > 0 else order.price

        # FIX #1: Calculate fees
        fee_rate = self._get_fee_rate(order.token_id)
        fee = total_cost * fee_rate

        if order.side == Side.BUY:
            self._set_cash(cash - total_cost - fee)
        else:
            self._set_cash(cash + total_cost - fee)
        self._update_position(order, total_shares, avg_price)

        now = int(time.time() * 1000)
        status = OrderStatus.FILLED if remaining <= 0 else OrderStatus.PARTIALLY_FILLED
        self.conn.execute(
            """INSERT INTO paper_trades
               (id, token_id, market_id, market_question, outcome, side,
                order_type, requested_price, filled_price, filled_size,
                total_cost, fee, status, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (trade_id, order.token_id, order.market_id, order.market_question,
             order.outcome, order.side.value, order.order_type.value,
             order.price, avg_price, total_shares, total_cost, fee,
             status.value, now),
        )
        self.conn.commit()

        fee_str = f" (fee ${fee:.2f})" if fee > 0 else ""
        logger.info(
            "PAPER LIMIT %s %s: %.2f shares @ avg $%.4f (cost $%.2f%s) | %s [%s]",
            order.side.value, order.outcome, total_shares, avg_price,
            total_cost, fee_str, order.market_question[:40], trade_id,
        )

        return OrderResult(
            order_id=trade_id,
            status=status,
            filled_price=avg_price,
            filled_size=total_shares,
            total_cost=total_cost,
        )

    def _get_held_shares(self, token_id: str) -> float:
        row = self.conn.execute(
            "SELECT shares FROM paper_positions WHERE token_id = ?",
            (token_id,),
        ).fetchone()
        return row["shares"] if row else 0.0

    def _update_position(self, order: TradeOrder, shares: float, price: float):
        """Update or create a position after a fill."""
        row = self.conn.execute(
            "SELECT * FROM paper_positions WHERE token_id = ?",
            (order.token_id,),
        ).fetchone()

        if order.side == Side.BUY:
            if row:
                old_shares = row["shares"]
                old_avg = row["avg_entry_price"]
                new_shares = old_shares + shares
                new_avg = ((old_shares * old_avg) + (shares * price)) / new_shares if new_shares > 0 else 0
                self.conn.execute(
                    "UPDATE paper_positions SET shares = ?, avg_entry_price = ? WHERE token_id = ?",
                    (new_shares, new_avg, order.token_id),
                )
            else:
                self.conn.execute(
                    """INSERT INTO paper_positions
                       (token_id, market_id, market_question, outcome, shares, avg_entry_price, realized_pnl)
                       VALUES (?, ?, ?, ?, ?, ?, 0)""",
                    (order.token_id, order.market_id, order.market_question,
                     order.outcome, shares, price),
                )
        else:  # SELL
            if not row or row["shares"] <= 0:
                # FIX #2: Should not reach here (checked earlier), but guard anyway
                return
            old_shares = row["shares"]
            old_avg = row["avg_entry_price"]
            sell_shares = min(shares, old_shares)
            realized = sell_shares * (price - old_avg)
            new_shares = old_shares - sell_shares

            # FIX #3: Preserve realized PnL — never delete, just zero out shares
            if new_shares <= 0.001:
                self.conn.execute(
                    "UPDATE paper_positions SET shares = 0, realized_pnl = realized_pnl + ? WHERE token_id = ?",
                    (realized, order.token_id),
                )
            else:
                self.conn.execute(
                    "UPDATE paper_positions SET shares = ?, realized_pnl = realized_pnl + ? WHERE token_id = ?",
                    (new_shares, realized, order.token_id),
                )

    def cancel_order(self, order_id: str) -> bool:
        result = self.conn.execute(
            "DELETE FROM paper_open_orders WHERE id = ?", (order_id,)
        )
        self.conn.commit()
        cancelled = result.rowcount > 0
        if cancelled:
            logger.info("PAPER cancelled order %s", order_id)
        return cancelled

    def get_positions(self) -> list[Position]:
        # Only return positions with shares > 0
        rows = self.conn.execute(
            "SELECT * FROM paper_positions WHERE shares > 0.001"
        ).fetchall()
        positions = []
        for r in rows:
            # FIX #4: Default unrealized to 0 and log errors
            current_price = None
            unrealized = 0.0
            try:
                snap = self.clob.get_price(r["token_id"], market_id=r["market_id"])
                current_price = snap.midpoint
                if current_price is not None:
                    unrealized = r["shares"] * (current_price - r["avg_entry_price"])
            except Exception as e:
                logger.warning("Failed to fetch price for %s: %s", r["token_id"][:30], e)

            positions.append(Position(
                token_id=r["token_id"],
                market_id=r["market_id"],
                market_question=r["market_question"],
                outcome=r["outcome"],
                shares=r["shares"],
                avg_entry_price=r["avg_entry_price"],
                current_price=current_price,
                unrealized_pnl=unrealized,
            ))
        return positions

    def get_portfolio(self) -> PortfolioSummary:
        cash = self._get_cash()
        positions = self.get_positions()

        total_position_value = sum(
            p.shares * (p.current_price or p.avg_entry_price)
            for p in positions
        )
        total_unrealized = sum(p.unrealized_pnl or 0 for p in positions)

        # FIX #3: Sum realized PnL from ALL positions (including closed ones with shares=0)
        realized_row = self.conn.execute(
            "SELECT COALESCE(SUM(realized_pnl), 0) as total FROM paper_positions"
        ).fetchone()
        total_realized = realized_row["total"]

        return PortfolioSummary(
            cash_balance=cash,
            positions=positions,
            total_position_value=total_position_value,
            total_equity=cash + total_position_value,
            total_realized_pnl=total_realized,
            total_unrealized_pnl=total_unrealized,
        )

    def get_balance(self) -> float:
        return self._get_cash()

    def get_trade_history(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM paper_trades ORDER BY timestamp DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def check_open_orders(self):
        """Check if any pending limit orders can now fill against live orderbook."""
        rows = self.conn.execute("SELECT * FROM paper_open_orders").fetchall()
        for r in rows:
            order = TradeOrder(
                token_id=r["token_id"],
                market_id=r["market_id"],
                market_question=r["market_question"],
                outcome=r["outcome"],
                side=Side(r["side"]),
                order_type=TradeOrderType.LIMIT,
                price=r["price"],
                size=r["size"] - r["filled_size"],
            )
            result = self._execute_limit_order(order)
            if result.status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED):
                self.conn.execute("DELETE FROM paper_open_orders WHERE id = ?", (r["id"],))
                self.conn.commit()

    def reset(self):
        """Reset all paper trading state back to starting balance."""
        starting = self.conn.execute(
            "SELECT value FROM paper_config WHERE key = 'starting_balance'"
        ).fetchone()
        balance = float(starting["value"]) if starting else 10_000.0

        self.conn.executescript("""
            DELETE FROM paper_trades;
            DELETE FROM paper_positions;
            DELETE FROM paper_open_orders;
        """)
        self._set_cash(balance)
        self._fee_cache.clear()
        self.conn.commit()
        logger.info("Paper trading reset. Balance: $%.2f", balance)

    def close(self):
        self.conn.close()
