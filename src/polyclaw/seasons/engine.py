"""SeasonEngine — lifecycle transitions, mark-to-market, finalization, composite metrics.

One engine per process; shares an Engine with TradingService.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, func, select, update

from polyclaw.storage.db import ensure_schema
from polyclaw.storage.schema import (
    agents,
    paper_trades,
    portfolio_snapshots,
    season_results,
    seasons,
)
from polyclaw.trading.clock import Clock, SystemClock

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SeasonRecord:
    id: str
    name: str
    starts_at_ms: int
    ends_at_ms: int
    starting_balance: float
    mode: str
    status: str
    registration_open: bool


@dataclass(frozen=True)
class LeaderboardEntry:
    agent_id: str
    name: str
    tier: str
    total_equity: float
    total_return: float
    sharpe: float | None
    max_drawdown: float
    calmar: float | None
    win_rate: float
    trade_count: int
    rank: int


class SeasonEngine:
    def __init__(self, engine: Engine, *, clock: Clock | None = None):
        self.engine = engine
        self.clock: Clock = clock or SystemClock()
        ensure_schema(engine)

    # ── CRUD ──────────────────────────────────────────────────

    def create_season(
        self,
        *,
        name: str,
        starts_at_ms: int,
        ends_at_ms: int,
        starting_balance: float = 10_000.0,
        mode: str = "paper",
        market_universe_filter: dict | None = None,
    ) -> str:
        season_id = str(uuid.uuid4())[:12]
        with self.engine.begin() as conn:
            conn.execute(
                seasons.insert().values(
                    id=season_id,
                    name=name,
                    starts_at_ms=starts_at_ms,
                    ends_at_ms=ends_at_ms,
                    starting_balance=starting_balance,
                    mode=mode,
                    market_universe_filter=json.dumps(market_universe_filter)
                    if market_universe_filter
                    else None,
                    status="draft",
                    registration_open=1,
                )
            )
        return season_id

    def get_season(self, season_id: str) -> SeasonRecord | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(seasons).where(seasons.c.id == season_id)).mappings().first()
        if row is None:
            return None
        return SeasonRecord(
            id=row["id"],
            name=row["name"],
            starts_at_ms=int(row["starts_at_ms"]),
            ends_at_ms=int(row["ends_at_ms"]),
            starting_balance=float(row["starting_balance"]),
            mode=row["mode"],
            status=row["status"],
            registration_open=bool(row["registration_open"]),
        )

    def list_seasons(self, *, status: str | None = None) -> list[SeasonRecord]:
        with self.engine.connect() as conn:
            q = select(seasons)
            if status:
                q = q.where(seasons.c.status == status)
            rows = conn.execute(q.order_by(seasons.c.starts_at_ms.desc())).mappings().all()
        return [
            SeasonRecord(
                id=r["id"],
                name=r["name"],
                starts_at_ms=int(r["starts_at_ms"]),
                ends_at_ms=int(r["ends_at_ms"]),
                starting_balance=float(r["starting_balance"]),
                mode=r["mode"],
                status=r["status"],
                registration_open=bool(r["registration_open"]),
            )
            for r in rows
        ]

    # ── Lifecycle transitions ─────────────────────────────────

    VALID_TRANSITIONS = {
        "draft": ["open_registration"],
        "open_registration": ["running"],
        "running": ["settling"],
        "settling": ["finalized"],
    }

    def transition(self, season_id: str, to_status: str) -> SeasonRecord:
        season = self.get_season(season_id)
        if season is None:
            raise ValueError(f"Season {season_id} not found")
        valid = self.VALID_TRANSITIONS.get(season.status, [])
        if to_status not in valid:
            raise ValueError(f"Cannot transition from {season.status} → {to_status}. Valid: {valid}")

        with self.engine.begin() as conn:
            values: dict[str, Any] = {"status": to_status}
            if to_status == "running":
                values["registration_open"] = 0
            conn.execute(update(seasons).where(seasons.c.id == season_id).values(**values))

        logger.info("Season %s transitioned %s → %s", season_id, season.status, to_status)
        return self.get_season(season_id)  # type: ignore[return-value]

    def start_season(self, season_id: str) -> SeasonRecord:
        """Convenience: draft → open_registration → running in one call."""
        season = self.get_season(season_id)
        if season is None:
            raise ValueError(f"Season {season_id} not found")
        if season.status == "draft":
            self.transition(season_id, "open_registration")
        return self.transition(season_id, "running")

    # ── Finalization (mark-to-market + compute rankings) ──────

    def finalize_season(self, season_id: str) -> list[LeaderboardEntry]:
        """Transition to settling → compute results → transition to finalized.
        Returns the ranked leaderboard."""
        season = self.get_season(season_id)
        if season is None:
            raise ValueError(f"Season {season_id} not found")
        if season.status == "running":
            self.transition(season_id, "settling")

        entries = self.compute_leaderboard(season_id)

        with self.engine.begin() as conn:
            # Clear old results for idempotency
            conn.execute(season_results.delete().where(season_results.c.season_id == season_id))
            for e in entries:
                conn.execute(
                    season_results.insert().values(
                        season_id=season_id,
                        agent_id=e.agent_id,
                        final_equity=e.total_equity,
                        total_return=e.total_return,
                        sharpe=e.sharpe,
                        max_drawdown=e.max_drawdown,
                        calmar=e.calmar,
                        win_rate=e.win_rate,
                        trade_count=e.trade_count,
                        rank=e.rank,
                    )
                )

        self.transition(season_id, "finalized")
        logger.info("Season %s finalized with %d agents ranked", season_id, len(entries))
        return entries

    # ── Composite leaderboard metrics ─────────────────────────

    def compute_leaderboard(self, season_id: str | None = None) -> list[LeaderboardEntry]:
        """Compute composite leaderboard from portfolio_snapshots + paper_trades.

        If season_id is given, only includes agents registered for that season and
        snapshots within the season's time window. If None, includes all agents.
        """
        with self.engine.connect() as conn:
            agent_rows = conn.execute(select(agents).where(agents.c.status == "active")).mappings().all()
            if season_id:
                season = self.get_season(season_id)
                if season:
                    agent_rows = [
                        r for r in agent_rows if r["season_id"] == season_id or r["season_id"] is None
                    ]

            entries: list[LeaderboardEntry] = []
            for agent_row in agent_rows:
                aid = agent_row["id"]
                starting = float(agent_row["starting_balance"])

                # Get portfolio snapshots for equity curve
                snaps = conn.execute(
                    select(portfolio_snapshots.c.ts_ms, portfolio_snapshots.c.total_equity)
                    .where(portfolio_snapshots.c.agent_id == aid)
                    .order_by(portfolio_snapshots.c.ts_ms)
                ).all()

                if not snaps:
                    entries.append(
                        LeaderboardEntry(
                            agent_id=aid,
                            name=agent_row["name"],
                            tier=agent_row["tier"],
                            total_equity=starting,
                            total_return=0.0,
                            sharpe=None,
                            max_drawdown=0.0,
                            calmar=None,
                            win_rate=0.0,
                            trade_count=0,
                            rank=0,
                        )
                    )
                    continue

                equities = [float(s[1]) for s in snaps]
                final_equity = equities[-1]
                total_return = (final_equity - starting) / starting if starting > 0 else 0.0

                # Sharpe from snapshot-to-snapshot returns
                sharpe = self._compute_sharpe(equities)
                max_dd = self._compute_max_drawdown(equities)
                calmar = (total_return / max_dd) if max_dd > 0.001 else None

                # Trade stats
                trade_count = conn.execute(
                    select(func.count()).select_from(paper_trades).where(paper_trades.c.agent_id == aid)
                ).scalar_one()
                winning = conn.execute(
                    select(func.count())
                    .select_from(paper_trades)
                    .where(paper_trades.c.agent_id == aid)
                    .where(paper_trades.c.side == "SELL")
                ).scalar_one()
                win_rate = winning / trade_count if trade_count > 0 else 0.0

                entries.append(
                    LeaderboardEntry(
                        agent_id=aid,
                        name=agent_row["name"],
                        tier=agent_row["tier"],
                        total_equity=final_equity,
                        total_return=total_return,
                        sharpe=sharpe,
                        max_drawdown=max_dd,
                        calmar=calmar,
                        win_rate=win_rate,
                        trade_count=int(trade_count),
                        rank=0,
                    )
                )

        # Rank by composite score (weighted)
        def _composite(e: LeaderboardEntry) -> float:
            s = e.total_return * 0.35
            s += (e.sharpe or 0) * 0.25
            s += (1 - e.max_drawdown) * 0.15  # lower DD = higher score
            s += (e.calmar or 0) * 0.10
            s += e.win_rate * 0.10
            s += min(e.trade_count / 100, 1.0) * 0.05  # anti-dust
            return s

        entries.sort(key=_composite, reverse=True)
        return [
            LeaderboardEntry(
                agent_id=e.agent_id,
                name=e.name,
                tier=e.tier,
                total_equity=e.total_equity,
                total_return=e.total_return,
                sharpe=e.sharpe,
                max_drawdown=e.max_drawdown,
                calmar=e.calmar,
                win_rate=e.win_rate,
                trade_count=e.trade_count,
                rank=i + 1,
            )
            for i, e in enumerate(entries)
        ]

    @staticmethod
    def _compute_sharpe(equities: list[float], periods_per_year: float = 365.0) -> float | None:
        if len(equities) < 3:
            return None
        returns = [
            (equities[i] - equities[i - 1]) / equities[i - 1]
            for i in range(1, len(equities))
            if equities[i - 1] > 0
        ]
        if not returns:
            return None
        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        std_r = math.sqrt(variance)
        if std_r < 1e-10:
            return 0.0
        return (mean_r / std_r) * math.sqrt(periods_per_year)

    @staticmethod
    def _compute_max_drawdown(equities: list[float]) -> float:
        if not equities:
            return 0.0
        peak = equities[0]
        max_dd = 0.0
        for e in equities:
            if e > peak:
                peak = e
            dd = (peak - e) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return max_dd

    # ── Auto-tick (called by worker loop) ─────────────────────

    def tick(self) -> None:
        """Called periodically by the worker. Handles automatic transitions."""
        now = self.clock.now_ms()
        for season in self.list_seasons(status="open_registration"):
            if now >= season.starts_at_ms:
                logger.info("Auto-starting season %s", season.id)
                self.transition(season.id, "running")
        for season in self.list_seasons(status="running"):
            if now >= season.ends_at_ms:
                logger.info("Auto-finalizing season %s", season.id)
                self.finalize_season(season.id)
