from polyclaw.backtest.strategy import Signal, Strategy, TickContext
from polyclaw.trading.models import Side


class MomentumStrategy(Strategy):
    """Buy when short MA crosses above long MA, sell when it crosses below."""

    name = "momentum"

    def __init__(self):
        self.short_window: int = 5
        self.long_window: int = 20
        self.trade_size: float = 100.0

    def on_tick(self, ctx: TickContext) -> Signal | None:
        if len(ctx.prices) < self.long_window + 1:
            return None

        short_ma = sum(ctx.prices[-self.short_window :]) / self.short_window
        long_ma = sum(ctx.prices[-self.long_window :]) / self.long_window

        prev_prices = ctx.prices[:-1]
        if len(prev_prices) < self.long_window:
            return None
        prev_short = sum(prev_prices[-self.short_window :]) / self.short_window
        prev_long = sum(prev_prices[-self.long_window :]) / self.long_window

        # Bullish crossover: short crosses above long
        if prev_short <= prev_long and short_ma > long_ma:
            if ctx.cash >= self.trade_size:
                return Signal(
                    side=Side.BUY,
                    size=self.trade_size,
                    reason=f"MA crossover up (short={short_ma:.4f} > long={long_ma:.4f})",
                )

        # Bearish crossover: short crosses below long
        if prev_short >= prev_long and short_ma < long_ma:
            if ctx.position_shares > 0:
                return Signal(
                    side=Side.SELL,
                    size=ctx.position_shares,
                    reason=f"MA crossover down (short={short_ma:.4f} < long={long_ma:.4f})",
                )

        return None
