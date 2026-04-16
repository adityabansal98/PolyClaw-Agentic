"""RiskGate — per-agent, per-tier order validation. Phase 3a.

Lives in `TradingService._check_risk` (Phase 2b stub replaced here). Both HTTP
callers and in-process agents hit this gate because both paths go through
TradingService — premise P1 from PLAN.md holds.

Checks (v1):
- `max_order_size_usdc`: reject orders larger than the tier cap.
- `max_position_size_usdc`: reject if filling this order would push the agent's
  total position (existing + new) above the cap.

Phase 4 will add per-season overrides and max_orders_per_min rate checks. The
error contract is stable: `RiskGateError` carries a machine-readable `code` so
the HTTP layer can surface `risk_gate.*` errors with full context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from polyclaw.agents.registry import AgentTier
from polyclaw.trading.models import TradeOrder


class RiskGateError(RuntimeError):
    """Raised when an order violates a risk-gate check.

    `code` is a stable machine-readable string matching the structured error
    contract from PLAN §7.3 (`risk_gate.max_order_size`, etc.).
    """

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


#: Default tier-specific limits. Phase 4 seasons can override.
@dataclass(frozen=True)
class TierLimits:
    max_order_size_usdc: float
    max_position_size_usdc: float


TIER_LIMITS: dict[str, TierLimits] = {
    AgentTier.HOSTED_INPROCESS.value: TierLimits(
        max_order_size_usdc=5_000.0,
        max_position_size_usdc=10_000.0,
    ),
    AgentTier.EXTERNAL_HTTP.value: TierLimits(
        max_order_size_usdc=500.0,
        max_position_size_usdc=2_000.0,
    ),
    AgentTier.EXTERNAL_MCP.value: TierLimits(
        max_order_size_usdc=500.0,
        max_position_size_usdc=2_000.0,
    ),
}

DEFAULT_LIMITS = TierLimits(max_order_size_usdc=500.0, max_position_size_usdc=2_000.0)


def check_risk(
    order: TradeOrder,
    *,
    agent_tier: str,
    current_position_usdc: float = 0.0,
) -> None:
    """Validate an order against the risk gate. Raises `RiskGateError` on violation."""
    limits = TIER_LIMITS.get(agent_tier, DEFAULT_LIMITS)

    if order.size > limits.max_order_size_usdc:
        raise RiskGateError(
            "risk_gate.max_order_size",
            f"Order size {order.size} exceeds max {limits.max_order_size_usdc} for tier {agent_tier}",
            details={
                "limit": limits.max_order_size_usdc,
                "current": order.size,
                "agent_tier": agent_tier,
            },
        )

    projected = current_position_usdc + order.size
    if projected > limits.max_position_size_usdc:
        raise RiskGateError(
            "risk_gate.max_position_size",
            f"Projected position {projected:.2f} exceeds max {limits.max_position_size_usdc} for tier {agent_tier}",
            details={
                "limit": limits.max_position_size_usdc,
                "current": current_position_usdc,
                "projected": projected,
                "agent_tier": agent_tier,
            },
        )
