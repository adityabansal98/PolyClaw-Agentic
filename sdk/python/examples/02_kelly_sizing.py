"""Cookbook 2: Kelly criterion sizing — bet proportional to edge.

Illustrates using get_portfolio + get_quota to size orders within risk limits.
"""

from polyclaw_sdk import PolyClawAgent


class KellySizingAgent(PolyClawAgent):
    def decide(self):
        portfolio = self.client.get_portfolio()
        quota = self.client.get_quota()
        max_order = quota.trading.get("max_order_size_usdc", 500)

        # Hypothetical edge: you'd compute this from signals / backtest
        edge = 0.08  # 8% expected edge
        win_prob = 0.55
        kelly_fraction = win_prob - (1 - win_prob) / (edge / (1 - edge)) if edge > 0 else 0
        kelly_fraction = max(0, min(kelly_fraction, 0.25))  # cap at 25%

        bet_size = min(portfolio.cash_balance * kelly_fraction, max_order)
        print(f"Kelly fraction: {kelly_fraction:.2%}, bet size: ${bet_size:.2f}")

        if bet_size > 1.0:
            result = self.client.place_market_order(
                token_id="YOUR_TOKEN",
                market_id="YOUR_MARKET",
                side="BUY",
                usdc=bet_size,
            )
            print(f"Placed: {result.status}")

        self.stop()


if __name__ == "__main__":
    KellySizingAgent(base_url="http://localhost:5000", token="YOUR_TOKEN").run()
