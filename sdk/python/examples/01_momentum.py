"""Cookbook 1: Momentum agent — backtest a momentum strategy, trade the winner.

Run with: python examples/01_momentum.py
"""

from polyclaw_sdk import PolyClawAgent


class MomentumAgent(PolyClawAgent):
    def decide(self):
        # 1. Check portfolio
        portfolio = self.client.get_portfolio()
        print(f"Cash: ${portfolio.cash_balance:.2f}")

        # 2. Enqueue a momentum backtest
        markets = [
            {"token_id": "YOUR_TOKEN_1", "market_id": "YOUR_MKT_1", "question": "Market 1", "outcome": "Yes"},
            {"token_id": "YOUR_TOKEN_2", "market_id": "YOUR_MKT_2", "question": "Market 2", "outcome": "Yes"},
        ]
        enq = self.client.enqueue_backtest(strategy="momentum", markets=markets, cash=1_000.0)
        print(f"Backtest {enq.backtest_id} enqueued")

        # 3. Wait for result
        run = self.client.wait_for_backtest(enq.backtest_id, timeout_s=60)
        if run.status == "failed":
            print(f"Backtest failed: {run.error}")
            return

        metrics = (run.result or {}).get("metrics", {})
        total_return = metrics.get("total_return", 0)
        print(f"Backtest return: {total_return:.2%}")

        # 4. If positive, buy into the first market
        if total_return > 0 and portfolio.cash_balance > 50:
            result = self.client.place_market_order(
                token_id=markets[0]["token_id"],
                market_id=markets[0]["market_id"],
                side="BUY",
                usdc=50.0,
            )
            print(f"Trade: {result.status} @ {result.filled_price}")

        self.stop()  # one-shot for the example


if __name__ == "__main__":
    MomentumAgent(base_url="http://localhost:5000", token="YOUR_TOKEN", interval_s=10).run()
