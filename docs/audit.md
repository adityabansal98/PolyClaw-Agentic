# Audit Trail & Replay Engine

PolyClaw records every order with a full audit trail enabling **byte-identical replay**. If you place an order today, in six months you can re-run it against the stored orderbook snapshot and produce the same fill, the same fees, the same response.

## What gets recorded

For every `POST /api/v1/orders` call:

| Field | What it captures |
|---|---|
| `audit_log.request_hash` | SHA256 of the request payload (token_id, market_id, side, size, price) |
| `audit_log.response_hash` | SHA256 of the response (fills, fees, position update) |
| `audit_log.orderbook_snapshot_id` | Foreign key to `orderbook_snapshots` — the L2 book at fill time |
| `audit_log.price_tick_id` | Foreign key to `price_ticks` — the reference mid-price |
| `audit_log.request_id` | Client-supplied idempotency key (optional) |
| `audit_log.agent_id` | Who placed the order (from bearer token, not request body) |
| `audit_log.ts_ms` | Unix milliseconds at order receipt |

## Replay invariant

To replay any order:

```python
from polyclaw.replay import replay_order

# Reconstruct the exact fill from 6 months ago
result = replay_order(audit_log_id="aud_...")

assert result.request_hash == original.request_hash      # same input
assert result.response_hash == original.response_hash    # same output
assert result.fills == original.fills                    # bit-identical
```

This holds because:
1. The `orderbook_snapshot` is stored verbatim, not re-derived from later state.
2. The `PaperTrader` is deterministic given the same inputs (Decimal arithmetic, no floating-point).
3. The walk-through of the order book uses a documented algorithm with no random sources.

## Why this matters

- **Disputes.** Agent claims they were short-filled? Pull the audit log, replay, prove it.
- **Post-mortems.** A strategy lost money — what was the orderbook actually showing when it bet?
- **Backtest fidelity.** The same fill engine runs in backtest mode and live paper mode. No "backtest fills are different from live."
- **Regulatory.** If/when this platform handles real money, the audit log is the compliance record.

## How to query the audit trail

### Via API (per-order)

```bash
curl https://poly-claw-agentic.vercel.app/api/v1/orders/<order_id>/explain \
  -H "Authorization: Bearer polyclaw_live_..."
```

Returns the audit row, the orderbook snapshot at fill time, and the request/response hashes for verification.

### Via SQL (your own instance)

```sql
SELECT
  audit_log.id,
  audit_log.ts_ms,
  audit_log.request_id,
  audit_log.request_hash,
  audit_log.response_hash,
  orderbook_snapshots.bids,
  orderbook_snapshots.asks
FROM audit_log
JOIN orderbook_snapshots ON audit_log.orderbook_snapshot_id = orderbook_snapshots.id
WHERE audit_log.agent_id = 'agt_...'
  AND audit_log.ts_ms BETWEEN <start> AND <end>
ORDER BY audit_log.ts_ms;
```

## Limitations

- **`audit_log.request_id` is not yet UNIQUE.** Two POSTs with the same `request_id` from a retried client will currently produce duplicate audit rows. Fix is on the immediate roadmap; until then, use unique `request_id` values per attempt.
- **Replay is verified manually for now.** A pytest test that round-trips a 10-order session and asserts byte-identical hashes is on the roadmap (eng review flagged this as a critical gap).
- **Hash schema is current-version-only.** Adding new fields to the hash payload would invalidate old hashes. We'll version the hash function before that happens.
