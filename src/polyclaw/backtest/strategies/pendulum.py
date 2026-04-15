from polyclaw.backtest.strategy import Signal, Strategy, TickContext
from polyclaw.trading.models import Side


class PendulumStrategy(Strategy):
    """NBA-style volatility harvesting — trades the swings, not the outcome.

    Targets evenly-matched markets (0.35-0.65 range) and profits from
    price oscillations. Buys dips, sells pops — captures bid-ask
    volatility regardless of final outcome.
    """

    name = "pendulum"

    def __init__(self):
        self.entry_low: float = 0.35  # only trade markets in this range
        self.entry_high: float = 0.65
        self.dip_pct: float = 0.05  # buy when price drops 5% from recent high
        self.pop_pct: float = 0.05  # sell when price rises 5% from recent low
        self.lookback: int = 10  # ticks to compute recent high/low
        self.trade_size: float = 150.0

    def on_tick(self, ctx: TickContext) -> Signal | None:
        # Only trade in the "pendulum zone"
        if ctx.price < self.entry_low or ctx.price > self.entry_high:
            # If we have a position outside the zone, close it
            if ctx.position_shares > 0:
                return Signal(
                    side=Side.SELL, size=ctx.position_shares, reason=f"Exit zone: price={ctx.price:.3f}"
                )
            return None

        if len(ctx.prices) < self.lookback + 1:
            return None

        recent = ctx.prices[-self.lookback :]
        recent_high = max(recent)
        recent_low = min(recent)

        # Buy on dip: price dropped significantly from recent high
        if recent_high > 0:
            drop_pct = (recent_high - ctx.price) / recent_high
            if drop_pct >= self.dip_pct and ctx.cash >= self.trade_size and ctx.position_shares == 0:
                return Signal(
                    side=Side.BUY,
                    size=self.trade_size,
                    reason=f"Dip buy: dropped {drop_pct * 100:.1f}% from {recent_high:.3f}",
                )

        # Sell on pop: price rose significantly from recent low
        if recent_low > 0 and ctx.position_shares > 0:
            rise_pct = (ctx.price - recent_low) / recent_low
            if rise_pct >= self.pop_pct:
                return Signal(
                    side=Side.SELL,
                    size=ctx.position_shares,
                    reason=f"Pop sell: rose {rise_pct * 100:.1f}% from {recent_low:.3f}",
                )

        return None
