import logging
import uuid
from datetime import datetime, timezone

from polyclaw.backtest.data_loader import MarketPriceData
from polyclaw.backtest.metrics import compute_metrics
from polyclaw.backtest.results import BacktestResult, EquityPoint, TradeRecord
from polyclaw.backtest.strategy import Signal, Strategy, TickContext
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

EQUITY_SAMPLE_INTERVAL = 50  # record equity every N ticks


class _Position:
    """Lightweight in-memory position tracker."""
    __slots__ = ("shares", "avg_entry", "realized_pnl", "market_id", "question", "outcome")

    def __init__(self, market_id: str = "", question: str = "", outcome: str = ""):
        self.shares = 0.0
        self.avg_entry = 0.0
        self.realized_pnl = 0.0
        self.market_id = market_id
        self.question = question
        self.outcome = outcome


class BacktestEngine(TraderInterface):
    """In-memory backtesting engine that replays historical prices."""

    def __init__(self, starting_cash: float = 10_000.0, fee_bps: int = 0):
        self._starting_cash = starting_cash
        self._cash = starting_cash
        self._fee_bps = fee_bps
        self._positions: dict[str, _Position] = {}
        self._current_prices: dict[str, float] = {}
        self._trades: list[TradeRecord] = []
        self._equity_curve: list[EquityPoint] = []
        self._current_ts: int = 0

    def _fee_rate(self) -> float:
        return self._fee_bps / 10_000

    def _position_value(self) -> float:
        return sum(
            pos.shares * self._current_prices.get(tid, pos.avg_entry)
            for tid, pos in self._positions.items()
            if pos.shares > 0
        )

    def _record_equity(self, timestamp: int):
        pv = self._position_value()
        self._equity_curve.append(EquityPoint(
            timestamp=timestamp,
            cash=round(self._cash, 4),
            position_value=round(pv, 4),
            total_equity=round(self._cash + pv, 4),
        ))

    # ── TraderInterface ─────────────────────────────────────

    def place_order(self, order: TradeOrder) -> OrderResult:
        price = self._current_prices.get(order.token_id)
        if price is None or price <= 0:
            return OrderResult(order_id="", status=OrderStatus.REJECTED, message="No price available")

        trade_id = uuid.uuid4().hex[:8]

        if order.side == Side.BUY:
            cost = min(order.size, self._cash)
            if cost <= 0:
                return OrderResult(order_id=trade_id, status=OrderStatus.REJECTED, message="No cash")
            fee = cost * self._fee_rate()
            shares = cost / price
            self._cash -= (cost + fee)

            pos = self._positions.setdefault(order.token_id, _Position(order.market_id, order.market_question, order.outcome))
            new_shares = pos.shares + shares
            pos.avg_entry = ((pos.shares * pos.avg_entry) + (shares * price)) / new_shares if new_shares > 0 else 0
            pos.shares = new_shares

            self._trades.append(TradeRecord(
                timestamp=self._current_ts, token_id=order.token_id,
                market_id=order.market_id, market_question=order.market_question,
                outcome=order.outcome, side="BUY", price=price,
                shares=round(shares, 4), cost=round(cost, 4), fee=round(fee, 4),
                reason=getattr(order, '_reason', ''),
            ))
            return OrderResult(order_id=trade_id, status=OrderStatus.FILLED,
                               filled_price=price, filled_size=shares, total_cost=cost)

        else:  # SELL
            pos = self._positions.get(order.token_id)
            if not pos or pos.shares <= 0:
                return OrderResult(order_id=trade_id, status=OrderStatus.REJECTED, message="No shares")
            sell_shares = min(order.size, pos.shares)
            proceeds = sell_shares * price
            fee = proceeds * self._fee_rate()
            realized = sell_shares * (price - pos.avg_entry)
            pos.shares -= sell_shares
            pos.realized_pnl += realized
            self._cash += (proceeds - fee)

            self._trades.append(TradeRecord(
                timestamp=self._current_ts, token_id=order.token_id,
                market_id=order.market_id, market_question=order.market_question,
                outcome=order.outcome, side="SELL", price=price,
                shares=round(sell_shares, 4), cost=round(proceeds, 4), fee=round(fee, 4),
                reason=getattr(order, '_reason', ''),
            ))
            return OrderResult(order_id=trade_id, status=OrderStatus.FILLED,
                               filled_price=price, filled_size=sell_shares, total_cost=proceeds)

    def cancel_order(self, order_id: str) -> bool:
        return False

    def get_positions(self) -> list[Position]:
        return [
            Position(
                token_id=tid, market_id=pos.market_id,
                market_question=pos.question, outcome=pos.outcome,
                shares=pos.shares, avg_entry_price=pos.avg_entry,
                current_price=self._current_prices.get(tid),
                unrealized_pnl=pos.shares * (self._current_prices.get(tid, pos.avg_entry) - pos.avg_entry),
            )
            for tid, pos in self._positions.items() if pos.shares > 0
        ]

    def get_portfolio(self) -> PortfolioSummary:
        positions = self.get_positions()
        pv = sum(p.shares * (p.current_price or p.avg_entry_price) for p in positions)
        return PortfolioSummary(
            cash_balance=self._cash, positions=positions,
            total_position_value=pv, total_equity=self._cash + pv,
            total_realized_pnl=sum(p.realized_pnl for p in self._positions.values()),
            total_unrealized_pnl=sum(p.unrealized_pnl or 0 for p in positions),
        )

    def get_balance(self) -> float:
        return self._cash

    # ── Backtest runner ─────────────────────────────────────

    def run(self, strategy: Strategy, market_data: list[MarketPriceData]) -> BacktestResult:
        started_at = datetime.now(timezone.utc).isoformat()

        # Build unified timeline: (timestamp, token_id, market_data_ref, price, tick_idx_in_market)
        timeline = []
        for md in market_data:
            for i, (ts, price) in enumerate(md.ticks):
                timeline.append((ts, md.token_id, md, price, i))
        timeline.sort(key=lambda x: x[0])

        # Pre-compute total ticks per market
        market_total_ticks = {md.token_id: len(md.ticks) for md in market_data}

        strategy.on_backtest_start()
        self._record_equity(timeline[0][0] if timeline else 0)

        for idx, (ts, token_id, md, price, tick_i) in enumerate(timeline):
            self._current_ts = ts
            self._current_prices[token_id] = price

            # Build price history up to this tick (no look-ahead)
            prices_so_far = [p for _, p in md.ticks[:tick_i + 1]]

            pos = self._positions.get(token_id)
            ctx = TickContext(
                timestamp=ts,
                token_id=token_id,
                market_id=md.market_id,
                market_question=md.market_question,
                price=price,
                prices=prices_so_far,
                cash=self._cash,
                position_shares=pos.shares if pos else 0.0,
                avg_entry_price=pos.avg_entry if pos else 0.0,
                tick_index=tick_i,
                total_ticks=market_total_ticks[token_id],
            )

            signal = strategy.on_tick(ctx)

            if signal is not None:
                order = TradeOrder(
                    token_id=token_id,
                    market_id=md.market_id,
                    market_question=md.market_question,
                    outcome=md.outcome,
                    side=signal.side,
                    order_type=TradeOrderType.MARKET,
                    size=signal.size,
                )
                order._reason = signal.reason
                self.place_order(order)
                self._record_equity(ts)
            elif idx % EQUITY_SAMPLE_INTERVAL == 0:
                self._record_equity(ts)

        # Final snapshot
        if timeline:
            self._record_equity(timeline[-1][0])

        strategy.on_backtest_end()
        finished_at = datetime.now(timezone.utc).isoformat()

        metrics = compute_metrics(self._trades, self._equity_curve, self._starting_cash)
        ending_equity = self._cash + self._position_value()

        return BacktestResult(
            backtest_id=uuid.uuid4().hex[:12],
            strategy_name=strategy.name,
            started_at=started_at,
            finished_at=finished_at,
            starting_cash=self._starting_cash,
            ending_cash=round(self._cash, 2),
            ending_equity=round(ending_equity, 2),
            fee_bps=self._fee_bps,
            fidelity=market_data[0].fidelity if market_data else 60,
            markets=[md.market_question for md in market_data],
            trades=self._trades,
            equity_curve=self._equity_curve,
            metrics=metrics,
            strategy_params={k: v for k, v in strategy.__dict__.items() if not k.startswith('_')},
        )
