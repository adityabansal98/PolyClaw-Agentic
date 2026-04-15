from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


@dataclass(frozen=True)
class AgentProfile:
    name: str
    strategy: str = "kelly"
    min_score: float = 0.55
    min_confidence: float = 0.55
    min_expected_value: float = 0.0
    fixed_bet_pct: float = 0.02
    kelly_multiplier: float = 0.5
    max_bet_pct: float = 0.08


@dataclass(frozen=True)
class BetDecision:
    should_bet: bool
    stake: float
    reason: str
    side: str | None = None


class Agent:
    def __init__(self, profile: AgentProfile):
        self.profile = profile

    @property
    def name(self) -> str:
        return self.profile.name

    def decide_bet(self, market_recommendation: dict[str, Any], *, balance: float) -> BetDecision:
        score = float(market_recommendation.get("score", 0.0) or 0.0)
        confidence = float(market_recommendation.get("confidence", 0.0) or 0.0)
        expected_value = float(market_recommendation.get("expected_value", 0.0) or 0.0)
        side = str(market_recommendation.get("side", "YES") or "YES").upper()
        if side not in {"YES", "NO"}:
            side = "YES"

        if score < self.profile.min_score:
            return BetDecision(False, 0.0, f"score {score:.3f} below {self.profile.min_score:.3f}")
        if confidence < self.profile.min_confidence:
            return BetDecision(
                False, 0.0, f"confidence {confidence:.3f} below {self.profile.min_confidence:.3f}"
            )
        if expected_value < self.profile.min_expected_value:
            return BetDecision(
                False, 0.0, f"ev {expected_value:.3f} below {self.profile.min_expected_value:.3f}"
            )
        if balance <= 0:
            return BetDecision(False, 0.0, "no balance")

        max_stake = balance * self.profile.max_bet_pct
        if self.profile.strategy == "fixed":
            stake = balance * self.profile.fixed_bet_pct
        else:
            kelly_fraction = float(market_recommendation.get("kelly_fraction", 0.0) or 0.0)
            if kelly_fraction <= 0:
                kelly_fraction = _clamp(expected_value * confidence, 0.0, self.profile.max_bet_pct)
            stake = balance * kelly_fraction * self.profile.kelly_multiplier

        stake = round(_clamp(stake, 0.0, max_stake), 2)
        if stake <= 0.0:
            return BetDecision(False, 0.0, "position size rounded to zero")
        return BetDecision(True, stake, "signal thresholds met", side=side)


def load_agents_from_config(config_path: str | Path) -> list[Agent]:
    payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
    rows = payload.get("agents", payload)
    if not isinstance(rows, list):
        raise ValueError("agent_config.json must contain a list or an object with an 'agents' list.")

    agents: list[Agent] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        profile = AgentProfile(
            name=name,
            strategy=str(row.get("strategy", "kelly")),
            min_score=float(row.get("min_score", 0.55)),
            min_confidence=float(row.get("min_confidence", 0.55)),
            min_expected_value=float(row.get("min_expected_value", 0.0)),
            fixed_bet_pct=float(row.get("fixed_bet_pct", 0.02)),
            kelly_multiplier=float(row.get("kelly_multiplier", 0.5)),
            max_bet_pct=float(row.get("max_bet_pct", 0.08)),
        )
        agents.append(Agent(profile))

    if not agents:
        raise ValueError("No valid agents found in config.")
    return agents
