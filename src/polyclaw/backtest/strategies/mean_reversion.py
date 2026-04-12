from polyclaw.backtest.strategy import Signal, Strategy, TickContext
from polyclaw.trading.models import Side


class MeanReversionStrategy(Strategy):
    """Buy when price dips below fair value, sell when it reverts.

    Assumes prediction markets revert toward an anchor price.
    """

    name = "mean_reversion"

    def __init__(self):
        self.anchor: float = 0.50
        self.entry_deviation: float = 0.08
        self.exit_deviation: float = 0.02
        self.trade_size: float = 100.0

    def on_tick(self, ctx: TickContext) -> Signal | None:
        distance_from_anchor = ctx.price - self.anchor

        # Buy when price drops far below anchor
        if distance_from_anchor < -self.entry_deviation and ctx.cash >= self.trade_size:
            return Signal(side=Side.BUY, size=self.trade_size,
                          reason=f"Price {ctx.price:.4f} below anchor {self.anchor} by {abs(distance_from_anchor):.4f}")

        # Sell when price reverts close to anchor
        if ctx.position_shares > 0 and abs(distance_from_anchor) < self.exit_deviation:
            return Signal(side=Side.SELL, size=ctx.position_shares,
                          reason=f"Price {ctx.price:.4f} reverted near anchor {self.anchor}")

        return None
