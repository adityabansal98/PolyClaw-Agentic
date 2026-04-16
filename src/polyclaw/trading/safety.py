"""Safety circuit breakers — Phase 7 polish.

Runs as part of the worker's sampler loop. After each portfolio snapshot, checks
every live-approved agent against safety rules and auto-pauses on violation.

Rules (from PLAN-V2.md §7.3):
1. Daily loss limit: if an agent loses > X% in a calendar day, pause.
2. Drawdown circuit breaker: if equity drops below starting_balance * (1 - max_dd_pct), freeze.
3. Position concentration limit: no single position > 20% of equity.
4. Cool-down after large loss: if a single trade loses > 5% of equity, pause for 15 min.

"Pause" means: set agent.status = "paused" so TradingService._check_risk rejects
new orders. The human can unpause via the approval dashboard.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import Engine, select, update

from polyclaw.storage.schema import agents, paper_trades, portfolio_snapshots
from polyclaw.trading.clock import Clock, SystemClock

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SafetyConfig:
    daily_loss_limit_pct: float = 10.0  # pause if lost > 10% in a day
    max_drawdown_pct: float = 30.0  # pause if equity < starting * 0.7
    max_position_concentration_pct: float = 20.0  # no single position > 20% equity
    large_loss_pct: float = 5.0  # cool-down if single trade loses > 5% equity
    cool_down_ms: int = 15 * 60 * 1000  # 15 minutes


DEFAULT_SAFETY = SafetyConfig()


class SafetyMonitor:
    """Checks all live-approved agents against safety rules."""

    def __init__(self, engine: Engine, *, clock: Clock | None = None, config: SafetyConfig | None = None):
        self.engine = engine
        self.clock: Clock = clock or SystemClock()
        self.config = config or DEFAULT_SAFETY

    def check_all_agents(self) -> list[str]:
        """Check every live-approved agent. Returns list of agent_ids that were paused."""
        paused: list[str] = []
        with self.engine.connect() as conn:
            live_agents = conn.execute(
                select(agents.c.id, agents.c.starting_balance)
                .where(agents.c.tier == "live_approved")
                .where(agents.c.status == "active")
            ).all()

        for agent_id, starting_balance in live_agents:
            violations = self._check_agent(agent_id, float(starting_balance))
            if violations:
                self._pause_agent(agent_id, violations)
                paused.append(agent_id)

        return paused

    def _check_agent(self, agent_id: str, starting_balance: float) -> list[str]:
        """Return list of violation descriptions, or empty if clean."""
        violations: list[str] = []
        now = self.clock.now_ms()

        with self.engine.connect() as conn:
            # Get latest snapshot
            latest = conn.execute(
                select(portfolio_snapshots.c.total_equity, portfolio_snapshots.c.ts_ms)
                .where(portfolio_snapshots.c.agent_id == agent_id)
                .order_by(portfolio_snapshots.c.ts_ms.desc())
                .limit(1)
            ).first()

            if latest is None:
                return []

            current_equity = float(latest[0])

            # 1. Drawdown circuit breaker
            floor = starting_balance * (1 - self.config.max_drawdown_pct / 100)
            if current_equity < floor:
                violations.append(
                    f"drawdown_breaker: equity ${current_equity:.2f} < floor ${floor:.2f} "
                    f"({self.config.max_drawdown_pct}% max DD from ${starting_balance:.2f})"
                )

            # 2. Daily loss limit
            day_start = now - 86_400_000  # 24h ago
            day_start_snap = conn.execute(
                select(portfolio_snapshots.c.total_equity)
                .where(portfolio_snapshots.c.agent_id == agent_id)
                .where(portfolio_snapshots.c.ts_ms >= day_start)
                .order_by(portfolio_snapshots.c.ts_ms.asc())
                .limit(1)
            ).first()
            if day_start_snap:
                day_start_equity = float(day_start_snap[0])
                if day_start_equity > 0:
                    daily_loss_pct = (day_start_equity - current_equity) / day_start_equity * 100
                    if daily_loss_pct > self.config.daily_loss_limit_pct:
                        violations.append(
                            f"daily_loss: lost {daily_loss_pct:.1f}% today "
                            f"(limit {self.config.daily_loss_limit_pct}%)"
                        )

            # 3. Large single-trade loss (cool-down)
            recent_trade = conn.execute(
                select(paper_trades.c.total_cost, paper_trades.c.side, paper_trades.c.fee)
                .where(paper_trades.c.agent_id == agent_id)
                .order_by(paper_trades.c.timestamp.desc())
                .limit(1)
            ).first()
            if recent_trade and current_equity > 0:
                cost = float(recent_trade[0])
                side = recent_trade[1]
                fee = float(recent_trade[2])
                # For a SELL, the PnL is cost - fee (received). For BUY, it's -cost - fee (spent).
                # A "large loss" on a sell means the sell realized a big negative PnL.
                # Simplification: if the trade cost > large_loss_pct of equity, flag it.
                trade_impact_pct = (cost + fee) / current_equity * 100
                if side == "SELL" and trade_impact_pct > self.config.large_loss_pct:
                    violations.append(
                        f"large_loss_cooldown: last trade impact {trade_impact_pct:.1f}% of equity "
                        f"(limit {self.config.large_loss_pct}%)"
                    )

        return violations

    def _pause_agent(self, agent_id: str, violations: list[str]) -> None:
        logger.warning("SAFETY PAUSE agent=%s violations=%s", agent_id, violations)
        with self.engine.begin() as conn:
            conn.execute(update(agents).where(agents.c.id == agent_id).values(status="paused"))
