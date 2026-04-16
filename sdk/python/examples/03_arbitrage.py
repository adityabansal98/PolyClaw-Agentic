"""Cookbook 3: Simple YES/NO arbitrage — if YES + NO prices < 1.00, buy both."""

from polyclaw_sdk import PolyClawAgent


class ArbitrageAgent(PolyClawAgent):
    def decide(self):
        portfolio = self.client.get_portfolio()
        # In production you'd scan markets via /api/v1/markets (Phase 4).
        # For this example, hardcode a pair.
        yes_token = "YOUR_YES_TOKEN"
        no_token = "YOUR_NO_TOKEN"
        market_id = "YOUR_MARKET_ID"

        # Check if the sum of YES + NO prices < 1.0 (arbitrage exists).
        # You'd fetch orderbooks here; placeholder logic:
        yes_price = 0.45
        no_price = 0.50
        total = yes_price + no_price

        if total < 0.98 and portfolio.cash_balance > 100:
            # Buy both sides — guaranteed profit at settlement.
            usdc_each = min(50.0, portfolio.cash_balance / 2)
            self.client.place_market_order(yes_token, market_id, side="BUY", usdc=usdc_each, outcome="Yes")
            self.client.place_market_order(no_token, market_id, side="BUY", usdc=usdc_each, outcome="No")
            print(f"Arbitrage: bought YES+NO for {total:.4f}, profit at settlement")
        else:
            print(f"No arb: YES+NO = {total:.4f}")

        self.stop()


if __name__ == "__main__":
    ArbitrageAgent(base_url="http://localhost:5000", token="YOUR_TOKEN").run()
