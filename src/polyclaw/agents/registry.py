"""Agent registry — manages `agents` + `agent_keys` rows.

Creates agents, issues bearer tokens, resolves tokens to agent ids. Used by:
- The dashboard auto-seed path (creates the `__dashboard__` agent on first boot)
- In-process agents (Phase 2b) that register at startup
- The HTTP auth middleware (Phase 3) that trades bearer tokens for agent ids
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import Engine, select, update

from polyclaw.storage.db import ensure_agent_row, ensure_schema
from polyclaw.storage.schema import agent_keys, agents
from polyclaw.trading.clock import Clock, SystemClock


class AgentTier(str, Enum):
    """The trust/rate-limit tier an agent runs under.

    - `hosted_inprocess`: trusted dev code running inside the platform process. Dev-
      only by default; production seasons reject it unless explicitly whitelisted
      (see premise P3 in PLAN.md).
    - `external_http`:    agents calling over HTTPS with a bearer key. The default
      production tier.
    - `external_mcp`:     agents connected via MCP (stdio/SSE). Phase 3+.
    """

    HOSTED_INPROCESS = "hosted_inprocess"
    EXTERNAL_HTTP = "external_http"
    EXTERNAL_MCP = "external_mcp"


@dataclass(frozen=True)
class AgentRecord:
    id: str
    name: str
    owner_contact: str
    created_at: int
    status: str
    season_id: str | None
    starting_balance: float
    tier: AgentTier


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AgentRegistry:
    """CRUD + key issuance for `agents`/`agent_keys`.

    One AgentRegistry per process, sharing an Engine with TradingService. Safe to
    construct and destroy freely — all state lives in the DB.
    """

    def __init__(self, engine: Engine, *, clock: Clock | None = None):
        self.engine = engine
        self.clock: Clock = clock or SystemClock()
        ensure_schema(engine)

    # ── Create / read ──────────────────────────────────────────

    def create_agent(
        self,
        agent_id: str,
        *,
        name: str,
        starting_balance: float = 10_000.0,
        tier: AgentTier = AgentTier.HOSTED_INPROCESS,
        owner_contact: str = "",
        season_id: str | None = None,
    ) -> AgentRecord:
        """Insert an agents row + seed `paper_config.cash_balance`. Idempotent:
        returns the existing record if `agent_id` is already present."""
        existing = self.get(agent_id)
        if existing is not None:
            return existing

        now = self.clock.now_ms()
        with self.engine.begin() as conn:
            conn.execute(
                agents.insert().values(
                    id=agent_id,
                    name=name,
                    owner_contact=owner_contact,
                    created_at=now,
                    status="active",
                    season_id=season_id,
                    starting_balance=starting_balance,
                    tier=tier.value,
                )
            )
        # Seed the paper_config cash row (idempotent; no-op if already present).
        ensure_agent_row(self.engine, agent_id, starting_balance)
        return AgentRecord(
            id=agent_id,
            name=name,
            owner_contact=owner_contact,
            created_at=now,
            status="active",
            season_id=season_id,
            starting_balance=starting_balance,
            tier=tier,
        )

    def get(self, agent_id: str) -> AgentRecord | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(agents).where(agents.c.id == agent_id)).mappings().first()
        if row is None:
            return None
        return AgentRecord(
            id=row["id"],
            name=row["name"],
            owner_contact=row["owner_contact"] or "",
            created_at=int(row["created_at"]),
            status=row["status"],
            season_id=row["season_id"],
            starting_balance=float(row["starting_balance"]),
            tier=AgentTier(row["tier"]),
        )

    def list_agents(self, *, status: str | None = "active") -> list[AgentRecord]:
        with self.engine.connect() as conn:
            q = select(agents)
            if status is not None:
                q = q.where(agents.c.status == status)
            rows = conn.execute(q.order_by(agents.c.created_at)).mappings().all()
        return [
            AgentRecord(
                id=r["id"],
                name=r["name"],
                owner_contact=r["owner_contact"] or "",
                created_at=int(r["created_at"]),
                status=r["status"],
                season_id=r["season_id"],
                starting_balance=float(r["starting_balance"]),
                tier=AgentTier(r["tier"]),
            )
            for r in rows
        ]

    # ── Bearer keys ────────────────────────────────────────────

    def issue_key(self, agent_id: str) -> str:
        """Mint a fresh bearer token for this agent. Returns the plaintext token —
        the registry only stores its SHA256 hash, so this is the caller's only
        chance to capture it.

        The token format is a URL-safe 32-byte base64 string prefixed with
        `polyclaw_live_` so it's greppable in logs / env files if leaked.
        """
        if self.get(agent_id) is None:
            raise KeyError(f"no such agent_id: {agent_id!r}")
        token = "polyclaw_live_" + secrets.token_urlsafe(32)
        key_hash = _hash_token(token)
        with self.engine.begin() as conn:
            conn.execute(
                agent_keys.insert().values(
                    agent_id=agent_id,
                    key_hash=key_hash,
                    created_at=self.clock.now_ms(),
                )
            )
        return token

    def resolve_key(self, token: str) -> str | None:
        """Return the agent_id for a bearer token, or None if unknown/revoked.

        Also bumps `last_used_at` on success so we can GC stale keys later.
        """
        key_hash = _hash_token(token)
        with self.engine.begin() as conn:
            row = conn.execute(
                select(agent_keys.c.agent_id, agent_keys.c.revoked_at).where(
                    agent_keys.c.key_hash == key_hash
                )
            ).first()
            if row is None or row[1] is not None:
                return None
            conn.execute(
                update(agent_keys)
                .where(agent_keys.c.key_hash == key_hash)
                .values(last_used_at=self.clock.now_ms())
            )
            return row[0]

    def revoke_key(self, token: str) -> bool:
        key_hash = _hash_token(token)
        with self.engine.begin() as conn:
            result = conn.execute(
                update(agent_keys)
                .where(agent_keys.c.key_hash == key_hash)
                .where(agent_keys.c.revoked_at.is_(None))
                .values(revoked_at=self.clock.now_ms())
            )
        return (result.rowcount or 0) > 0
