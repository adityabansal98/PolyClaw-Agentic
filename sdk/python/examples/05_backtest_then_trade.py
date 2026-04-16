"""Cookbook 5: Backtest-then-trade — the canonical research loop.

1. Enqueue a backtest for a strategy + market universe.
2. Wait for the result.
3. If the strategy shows positive risk-adjusted return, execute a trade.
4. Check the explain endpoint to verify what happened.

This is the simplest complete example of the research-then-trade flow the
platform is designed to serve.
"""

from polyclaw_sdk import PolyClawClient


def main():
    client = PolyClawClient(base_url="http://localhost:5000", token="YOUR_TOKEN")

    # 1. Enqueue
    markets = [
        {"token_id": "YOUR_TOKEN_1", "market_id": "YOUR_MKT_1", "question": "Will X happen?", "outcome": "Yes"},
    ]
    enq = client.enqueue_backtest(strategy="momentum", markets=markets, cash=1_000.0)
    print(f"Backtest enqueued: {enq.backtest_id}")

    # 2. Wait
    run = client.wait_for_backtest(enq.backtest_id, timeout_s=120)
    if run.status == "failed":
        print(f"Failed: {run.error}")
        return

    metrics = (run.result or {}).get("metrics", {})
    sharpe = metrics.get("sharpe", 0)
    total_return = metrics.get("total_return", 0)
    print(f"Backtest: return={total_return:.2%}, sharpe={sharpe:.2f}")

    # 3. Trade if positive
    if total_return > 0 and sharpe > 0.5:
        result = client.place_market_order(
            token_id=markets[0]["token_id"],
            market_id=markets[0]["market_id"],
            side="BUY",
            usdc=50.0,
        )
        print(f"Trade: {result.status}, filled {result.filled_size} @ {result.filled_price}")

        # 4. Explain the fill
        explain = client.explain_order(result.order_id)
        print(f"Audit: snapshot_id={explain.get('audit', {}).get('orderbook_snapshot_id')}")
    else:
        print("No trade — strategy didn't pass the bar")

    client.close()


if __name__ == "__main__":
    main()
