"""Cookbook 4: LLM-driven agent — Claude analyzes the portfolio and decides.

Requires: `pip install anthropic`

This example shows the "Claude-in-the-loop" pattern: the agent fetches portfolio
state, sends it to Claude as structured context, asks for a trading decision, and
executes whatever Claude returns. The agent brings its own LLM key.
"""

from __future__ import annotations

import json
import os

from polyclaw_sdk import PolyClawAgent


class LLMDrivenAgent(PolyClawAgent):
    def on_start(self):
        try:
            import anthropic

            self.llm = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        except ImportError:
            print("pip install anthropic  # required for this example")
            self.stop()

    def decide(self):
        portfolio = self.client.get_portfolio()
        positions = self.client.get_positions()

        context = json.dumps(
            {
                "cash": portfolio.cash_balance,
                "equity": portfolio.total_equity,
                "positions": [
                    {"token_id": p.token_id, "shares": p.shares, "avg_entry": p.avg_entry_price}
                    for p in positions
                ],
            },
            indent=2,
        )

        response = self.llm.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"You are a prediction-market trading agent. Here is your current portfolio:\n\n"
                        f"```json\n{context}\n```\n\n"
                        f"Respond with a JSON object: "
                        f'{{"action": "buy"|"sell"|"hold", "token_id": "...", "market_id": "...", '
                        f'"usdc": <number>, "reasoning": "..."}}'
                    ),
                }
            ],
        )

        decision = json.loads(response.content[0].text)
        print(f"Claude says: {decision['action']} — {decision.get('reasoning', '')[:80]}")

        if decision["action"] == "buy" and decision.get("token_id"):
            self.client.place_market_order(
                token_id=decision["token_id"],
                market_id=decision.get("market_id", ""),
                side="BUY",
                usdc=float(decision.get("usdc", 10)),
            )
        elif decision["action"] == "sell" and decision.get("token_id"):
            self.client.place_market_order(
                token_id=decision["token_id"],
                market_id=decision.get("market_id", ""),
                side="SELL",
                usdc=float(decision.get("usdc", 10)),
            )

        self.stop()


if __name__ == "__main__":
    LLMDrivenAgent(base_url="http://localhost:5000", token="YOUR_TOKEN").run()
