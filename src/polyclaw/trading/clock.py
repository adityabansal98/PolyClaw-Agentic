"""Clock abstraction for deterministic replay.

Every timestamp in the trading path must come from an injected `Clock`. Production uses
`SystemClock` (wall clock). Replay and tests use `VirtualClock` which advances only when
explicitly told to, producing byte-identical runs across executions.

This is load-bearing for Phase 1's replay invariant: if even one `time.time()` slips
through to `_execute_market_order` / audit writes, two replays of the same audit log
will disagree and the replay test breaks.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod


class Clock(ABC):
    """Abstract monotonic clock. All trading-path timestamps go through this."""

    @abstractmethod
    def now_ms(self) -> int:
        """Current time as unix ms (int). Must be monotonically non-decreasing."""
        ...


class SystemClock(Clock):
    """Wall-clock implementation for production."""

    def now_ms(self) -> int:
        return int(time.time() * 1000)


class VirtualClock(Clock):
    """Test / replay clock. Advances only via `advance()` or by explicit `set()`.

    Two runs started at the same `start_ms` and advanced identically produce the same
    timestamp stream, which is what makes golden-file replay tests possible.
    """

    def __init__(self, start_ms: int = 0, step_ms: int = 1000):
        self._now = int(start_ms)
        self._step = int(step_ms)

    def now_ms(self) -> int:
        return self._now

    def advance(self, ms: int | None = None) -> int:
        self._now += int(ms) if ms is not None else self._step
        return self._now

    def set(self, ms: int) -> None:
        self._now = int(ms)
