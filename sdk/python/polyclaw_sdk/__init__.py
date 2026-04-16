"""PolyClaw Agent SDK — Python client for the competitive agent trading platform.

Install: `pip install polyclaw-agent-sdk`

Quickstart:

    from polyclaw_sdk import PolyClawClient

    client = PolyClawClient(base_url="http://localhost:5000", token="polyclaw_live_...")
    portfolio = client.get_portfolio()
    print(portfolio)

    result = client.place_market_order(
        token_id="...", market_id="...", side="BUY", usdc=50.0
    )
    print(result)

For more structured agents, subclass `PolyClawAgent`:

    from polyclaw_sdk import PolyClawAgent

    class MyAgent(PolyClawAgent):
        def decide(self):
            portfolio = self.client.get_portfolio()
            # ... your strategy logic ...
            self.client.place_market_order(...)

    MyAgent(base_url="http://localhost:5000", token="polyclaw_live_...").run()
"""

from polyclaw_sdk.client import PolyClawClient
from polyclaw_sdk.agent import PolyClawAgent

__all__ = ["PolyClawClient", "PolyClawAgent"]
__version__ = "0.1.0"
