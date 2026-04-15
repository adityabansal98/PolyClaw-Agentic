from polyclaw.backtest.strategy import Signal, Strategy, TickContext
from polyclaw.trading.models import Side


class ThresholdStrategy(Strategy):
    """Buy when price drops below a threshold, sell when it rises above another.

    The simplest possible strategy for demonstration.
    """

    name = "threshold"

    def __init__(self):
        self.buy_below: float = 0.35
        self.sell_above: float = 0.65
        self.trade_size: float = 100.0

    def on_tick(self, ctx: TickContext) -> Signal | None:
        if ctx.price < self.buy_below and ctx.cash >= self.trade_size:
            return Signal(
                side=Side.BUY, size=self.trade_size, reason=f"Price {ctx.price:.4f} < {self.buy_below}"
            )

        if ctx.price > self.sell_above and ctx.position_shares > 0:
            return Signal(
                side=Side.SELL, size=ctx.position_shares, reason=f"Price {ctx.price:.4f} > {self.sell_above}"
            )

        return None
