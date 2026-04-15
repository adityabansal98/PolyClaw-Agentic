"""Phase 2a tests — price_ticks store, PriceTickIngester, PostgresSource, and the
Phase 1 replay completeness check.

Parametrized across SQLite and Postgres via the `engine` fixture from conftest.py.
The replay completeness test is the marquee item: it proves that an `audit_log` +
`orderbook_snapshots` row pair is sufficient to replay a Phase 1 trade bit-for-bit,
which is what Phase 1's success criterion §10.8 ("Phase 1 trades are replayable
end-to-end from `price_ticks` + `orderbook_snapshots` + `audit_log`") actually asks for.
"""

from __future__ import annotations

from sqlalchemy import Engine, select

from polyclaw.backtest.data_loader import PostgresSource
from polyclaw.ingestion.backfill_price_ticks import backfill_tokens
from polyclaw.ingestion.price_ingester import (
    SOURCE_BACKFILL,
    PriceTickIngester,
)
from polyclaw.models.orderbook import OrderBook, OrderLevel
from polyclaw.models.price import PriceSnapshot
from polyclaw.storage.schema import audit_log, orderbook_snapshots, paper_trades, price_ticks
from polyclaw.trading.clock import VirtualClock
from polyclaw.trading.market_data import ReplayMarketDataProvider, orderbook_from_json
from polyclaw.trading.models import OrderStatus, Side, TradeOrder, TradeOrderType
from polyclaw.trading.paper_trader import PaperTrader

# ── Fake clob for ingester tests ──────────────────────────────────────────


class _FakeClob:
    """Minimal stub matching the ClobClientWrapper interface we actually use."""

    def __init__(self, snapshots: list[PriceSnapshot]):
        self.snapshots = snapshots
        self.calls = 0

    def get_prices_batch(self, token_ids, token_to_market=None):
        self.calls += 1
        return self.snapshots


# ── Test: ingester dedup on unchanged price ───────────────────────────────


def test_price_ingester_dedup(engine: Engine):
    """Identical consecutive prices must not produce duplicate rows."""
    clock = VirtualClock(start_ms=1_700_000_000_000)
    clob = _FakeClob(
        [
            PriceSnapshot(token_id="t1", market_id="m1", midpoint=0.42, timestamp=0),
            PriceSnapshot(token_id="t2", market_id="m1", midpoint=0.58, timestamp=0),
        ]
    )
    ing = PriceTickIngester(engine, clob=clob, clock=clock)

    r1 = ing.ingest_tokens(["t1", "t2"])
    assert (r1.fetched, r1.inserted, r1.deduped) == (2, 2, 0)

    clock.advance(60_000)
    r2 = ing.ingest_tokens(["t1", "t2"])
    assert (r2.fetched, r2.inserted, r2.deduped) == (2, 0, 2)

    # Exactly 2 rows, one per token.
    with engine.connect() as conn:
        rows = conn.execute(select(price_ticks)).all()
    assert len(rows) == 2


def test_price_ingester_change(engine: Engine):
    """A price change produces exactly one new row for the changed token."""
    clock = VirtualClock(start_ms=1_700_000_000_000)
    clob = _FakeClob(
        [
            PriceSnapshot(token_id="t1", market_id="m1", midpoint=0.42, timestamp=0),
            PriceSnapshot(token_id="t2", market_id="m1", midpoint=0.58, timestamp=0),
        ]
    )
    ing = PriceTickIngester(engine, clob=clob, clock=clock)
    ing.ingest_tokens(["t1", "t2"])

    clock.advance(60_000)
    clob.snapshots = [
        PriceSnapshot(token_id="t1", market_id="m1", midpoint=0.45, timestamp=0),
        PriceSnapshot(token_id="t2", market_id="m1", midpoint=0.58, timestamp=0),
    ]
    r = ing.ingest_tokens(["t1", "t2"])
    assert (r.inserted, r.deduped) == (1, 1)

    with engine.connect() as conn:
        rows = conn.execute(select(price_ticks).order_by(price_ticks.c.ts_ms, price_ticks.c.token_id)).all()
    assert len(rows) == 3  # 2 initial + 1 changed


# ── Test: retention prune ─────────────────────────────────────────────────


def test_retention_prune(engine: Engine):
    """`prune_older_than` drops rows beyond the retention window."""
    clock = VirtualClock(start_ms=1_700_000_000_000)
    clob = _FakeClob([PriceSnapshot(token_id="t1", market_id="m1", midpoint=0.1, timestamp=0)])
    ing = PriceTickIngester(engine, clob=clob, clock=clock)

    ing.ingest_tokens(["t1"])  # old row at t=1.7e12

    # Jump 10 days forward and insert a new tick
    clock.advance(10 * 86_400_000)
    clob.snapshots = [PriceSnapshot(token_id="t1", market_id="m1", midpoint=0.2, timestamp=0)]
    ing.ingest_tokens(["t1"])

    # Prune anything older than 5 days — should drop the first tick
    deleted = ing.prune_older_than(days=5)
    assert deleted == 1

    with engine.connect() as conn:
        rows = conn.execute(select(price_ticks.c.price)).all()
    assert len(rows) == 1
    assert rows[0][0] == 0.2


# ── Test: PostgresSource round-trip ───────────────────────────────────────


def test_postgres_source_loads_ticks(engine: Engine):
    """PostgresSource returns the ticks written by the ingester, sorted by time."""
    clock = VirtualClock(start_ms=1_700_000_000_000)
    clob = _FakeClob([PriceSnapshot(token_id="t1", market_id="m1", midpoint=0.40, timestamp=0)])
    ing = PriceTickIngester(engine, clob=clob, clock=clock)

    # Write 3 ticks at different times by mutating the fake clob's price.
    prices = [0.40, 0.41, 0.42]
    for p in prices:
        clob.snapshots = [PriceSnapshot(token_id="t1", market_id="m1", midpoint=p, timestamp=0)]
        ing.ingest_tokens(["t1"])
        clock.advance(60_000)

    src = PostgresSource(engine)
    ticks = src.load_ticks("t1", fidelity=1)  # fidelity=1s → no thinning
    assert [p for _, p in ticks] == prices
    # Timestamps are monotonically increasing
    assert ticks[0][0] < ticks[1][0] < ticks[2][0]


def test_postgres_source_fidelity_thinning(engine: Engine):
    """PostgresSource thins ticks denser than `fidelity` seconds apart."""
    clock = VirtualClock(start_ms=1_700_000_000_000)
    clob = _FakeClob([PriceSnapshot(token_id="t1", market_id="m1", midpoint=0.40, timestamp=0)])
    ing = PriceTickIngester(engine, clob=clob, clock=clock)

    for i in range(5):
        clob.snapshots = [PriceSnapshot(token_id="t1", market_id="m1", midpoint=0.40 + 0.01 * i, timestamp=0)]
        ing.ingest_tokens(["t1"])
        clock.advance(30_000)  # 30s steps

    src = PostgresSource(engine)
    # fidelity=60s → every other tick is kept
    ticks = src.load_ticks("t1", fidelity=60)
    assert len(ticks) == 3  # t0, t0+60s, t0+120s (the 4th at +90s is thinned)


# ── Test: backfill writes rows tagged as backfill ─────────────────────────


def test_backfill_writes_rows(engine: Engine, monkeypatch):
    """backfill_tokens seeds price_ticks with source=backfill."""
    import polyclaw.ingestion.backfill_price_ticks as backfill_mod

    class _StubSource:
        def load_ticks(self, token_id, *, fidelity):
            return [(1_700_000_000_000, 0.40), (1_700_000_060_000, 0.41)]

    monkeypatch.setattr(backfill_mod, "ClobSource", _StubSource)

    count = backfill_tokens(engine, ["tok_backfill"], fidelity=60)
    assert count == 2

    with engine.connect() as conn:
        rows = conn.execute(
            select(price_ticks.c.source, price_ticks.c.price)
            .where(price_ticks.c.token_id == "tok_backfill")
            .order_by(price_ticks.c.ts_ms)
        ).all()
    assert [r[0] for r in rows] == [SOURCE_BACKFILL, SOURCE_BACKFILL]
    assert [r[1] for r in rows] == [0.40, 0.41]


# ── Test: Phase 1 replay completeness ─────────────────────────────────────


def test_phase1_replay_completeness(engine: Engine, tmp_path):
    """Record a Phase 1 session, rehydrate a ReplayMarketDataProvider from
    `audit_log` + `orderbook_snapshots`, replay, diff trade stream + hashes.

    This is the load-bearing assertion behind PLAN §10.8: a trade is replayable
    from the stored audit + snapshot data alone, without any live state. If this
    test ever fails, the replay invariant is broken and Phase 1 needs to be
    revisited.
    """
    from polyclaw.storage.db import make_engine

    # ── Record run ──
    eng_record = make_engine(f"sqlite:///{tmp_path}/record.db")
    clock_record = VirtualClock(start_ms=1_700_000_000_000)
    provider_record = ReplayMarketDataProvider()

    book_a = OrderBook(
        token_id="t1",
        market_id="m1",
        bids=[OrderLevel(price=0.40, size=1000.0)],
        asks=[OrderLevel(price=0.42, size=1000.0)],
        best_bid=0.40,
        best_ask=0.42,
        midpoint=0.41,
        spread=0.02,
        timestamp=0,
    )
    book_b = OrderBook(
        token_id="t1",
        market_id="m1",
        bids=[OrderLevel(price=0.43, size=1000.0)],
        asks=[OrderLevel(price=0.45, size=1000.0)],
        best_bid=0.43,
        best_ask=0.45,
        midpoint=0.44,
        spread=0.02,
        timestamp=0,
    )
    provider_record.add("t1", clock_record.now_ms(), book_a)

    trader = PaperTrader(
        agent_id="alice",
        engine=eng_record,
        clock=clock_record,
        market_data=provider_record,
        starting_balance=1_000.0,
    )

    # Trade 1 against book_a
    r1 = trader.place_order(
        TradeOrder(
            token_id="t1",
            market_id="m1",
            outcome="Yes",
            side=Side.BUY,
            order_type=TradeOrderType.MARKET,
            size=50.0,
        )
    )
    assert r1.status == OrderStatus.FILLED

    # Advance clock, swap in a new book, trade again
    clock_record.advance(60_000)
    provider_record.add("t1", clock_record.now_ms(), book_b)
    r2 = trader.place_order(
        TradeOrder(
            token_id="t1",
            market_id="m1",
            outcome="Yes",
            side=Side.SELL,
            order_type=TradeOrderType.MARKET,
            size=20.0,
        )
    )
    assert r2.status == OrderStatus.FILLED

    # ── Pull audit rows + snapshot bodies (the "golden file") ──
    with eng_record.connect() as conn:
        audit_rows = conn.execute(
            select(
                audit_log.c.ts_ms,
                audit_log.c.orderbook_snapshot_id,
                audit_log.c.request_hash,
                audit_log.c.response_hash,
            )
            .where(audit_log.c.agent_id == "alice")
            .order_by(audit_log.c.ts_ms, audit_log.c.id)
        ).all()
        original_trades = [
            dict(r)
            for r in conn.execute(
                select(paper_trades)
                .where(paper_trades.c.agent_id == "alice")
                .order_by(paper_trades.c.timestamp)
            )
            .mappings()
            .all()
        ]
        # Build {snapshot_id: (token_id, ts_ms, book)} from orderbook_snapshots
        snap_map: dict[int, tuple[str, int, OrderBook]] = {}
        for r in conn.execute(select(orderbook_snapshots)).mappings().all():
            snap_map[int(r["id"])] = (r["token_id"], int(r["ts_ms"]), orderbook_from_json(r["snapshot_json"]))

    eng_record.dispose()

    # ── Replay run: fresh DB, fresh provider rehydrated from snapshots ──
    eng_replay = make_engine(f"sqlite:///{tmp_path}/replay.db")
    clock_replay = VirtualClock(start_ms=1_700_000_000_000)
    provider_replay = ReplayMarketDataProvider()
    for token_id, ts_ms, book in snap_map.values():
        provider_replay.add(token_id, ts_ms, book)

    replayer = PaperTrader(
        agent_id="alice",
        engine=eng_replay,
        clock=clock_replay,
        market_data=provider_replay,
        starting_balance=1_000.0,
    )

    # Replay issues the same orders at the same clock positions. Orders themselves
    # are not stored in audit_log (only their hashes), so the test drives them
    # explicitly — the point of this test is that the *output* bytes match, not
    # that orders can be recovered from hashes (they can't; hashes are one-way).
    clock_replay.set(audit_rows[0][0])
    replayer.place_order(
        TradeOrder(
            token_id="t1",
            market_id="m1",
            outcome="Yes",
            side=Side.BUY,
            order_type=TradeOrderType.MARKET,
            size=50.0,
        )
    )
    clock_replay.set(audit_rows[1][0])
    replayer.place_order(
        TradeOrder(
            token_id="t1",
            market_id="m1",
            outcome="Yes",
            side=Side.SELL,
            order_type=TradeOrderType.MARKET,
            size=20.0,
        )
    )

    with eng_replay.connect() as conn:
        replay_trades = [
            dict(r)
            for r in conn.execute(
                select(paper_trades)
                .where(paper_trades.c.agent_id == "alice")
                .order_by(paper_trades.c.timestamp)
            )
            .mappings()
            .all()
        ]
        replay_audits = conn.execute(
            select(audit_log.c.request_hash, audit_log.c.response_hash)
            .where(audit_log.c.agent_id == "alice")
            .order_by(audit_log.c.ts_ms, audit_log.c.id)
        ).all()
    eng_replay.dispose()

    # Trade IDs are random per-run; strip them before comparing.
    def _strip(rows):
        return [{k: v for k, v in r.items() if k != "id"} for r in rows]

    assert _strip(original_trades) == _strip(replay_trades), "trade stream diverged in replay"

    # The request/response hashes are content-derived — if the fill output is
    # byte-identical, these match exactly.
    original_hashes = [(r[2], r[3]) for r in audit_rows]
    replay_hashes = [(r[0], r[1]) for r in replay_audits]
    assert original_hashes == replay_hashes, "audit hashes diverged in replay"
