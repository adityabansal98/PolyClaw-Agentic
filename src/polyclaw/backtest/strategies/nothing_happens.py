from polyclaw.backtest.strategy import Signal, Strategy, TickContext
from polyclaw.trading.models import Side


class NothingHappensStrategy(Strategy):
    """Contrarian "Nothing Ever Happens" fading strategy.

    90% of news-driven price spikes revert to baseline.
    Detects sudden price jumps and bets on mean reversion.
    Shorts the spike by selling YES positions or avoiding buys.
    """

    name = "nothing_happens"

    def __init__(self):
        self.spike_threshold: float = 0.08  # 8% price jump = spike
        self.lookback_ticks: int = 5  # check last 5 ticks for spike
        self.reversion_tolerance: float = 0.02  # exit when within 2% of pre-spike
        self.trade_size: float = 200.0
        self._pre_spike_price: dict[str, float] = {}

    def on_backtest_start(self) -> None:
        self._pre_spike_price = {}

    def on_tick(self, ctx: TickContext) -> Signal | None:
        if len(ctx.prices) < self.lookback_ticks + 1:
            return None

        # Compute price change over lookback window
        baseline = ctx.prices[-(self.lookback_ticks + 1)]
        change = ctx.price - baseline
        change_pct = change / baseline if baseline > 0 else 0

        # Detect upward spike
        if change_pct > self.spike_threshold and ctx.position_shares == 0:
            # Price spiked up — bet it reverts (don't buy, or sell if holding)
            # Record pre-spike level for exit target
            self._pre_spike_price[ctx.token_id] = baseline

            # Buy at the spike (counterintuitive: we're buying to SELL later on reversion)
            # Actually for "nothing happens": we want to SHORT the spike
            # Since we can't short in this engine, we skip buying during spikes
            # and instead buy during the reversion
            return None

        # Detect downward spike (overreaction to bad news)
        if change_pct < -self.spike_threshold and ctx.cash >= self.trade_size:
            # Price crashed — bet it reverts up
            self._pre_spike_price[ctx.token_id] = baseline
            return Signal(
                side=Side.BUY,
                size=self.trade_size,
                reason=f"Fade crash: dropped {change_pct * 100:.1f}%, expect reversion to {baseline:.3f}",
            )

        # Check for reversion exit
        pre_spike = self._pre_spike_price.get(ctx.token_id)
        if pre_spike is not None and ctx.position_shares > 0:
            distance = abs(ctx.price - pre_spike)
            if distance <= self.reversion_tolerance:
                # Price reverted — take profit
                del self._pre_spike_price[ctx.token_id]
                return Signal(
                    side=Side.SELL,
                    size=ctx.position_shares,
                    reason=f"Reversion complete: price={ctx.price:.3f} near pre-spike={pre_spike:.3f}",
                )

            # Stop loss: if price moved further away from pre-spike (spike continued)
            if ctx.price < pre_spike * 0.85:
                del self._pre_spike_price[ctx.token_id]
                return Signal(
                    side=Side.SELL,
                    size=ctx.position_shares,
                    reason=f"Stop loss: spike continued, price={ctx.price:.3f} vs target={pre_spike:.3f}",
                )

        return None
