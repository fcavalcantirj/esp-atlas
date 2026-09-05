"""EspAtlas Jr — the tick's budget (jr/budget.py): GitHub calls and wall-clock, counted, capped.

PLAN §3.2: one hourly tick targets < 6 minutes and < 150 GitHub API calls, and a stage that
runs over either is ABORTED, never allowed to drag the next tick into a rate-limit hole. This
module is that counter. It is deliberately dumb: no retries, no backoff — a stage that needs
more than the budget has a design problem, and the report line will say so.

`clock` is injectable (defaults to time.monotonic) so tests can move time by hand.
"""
from __future__ import annotations

import time

DEFAULT_MAX_CALLS = 150
DEFAULT_MAX_SECONDS = 360.0


class BudgetExceeded(RuntimeError):
    """Raised by charge() when the next call would cross the cap. The tick catches it once, at
    the top, and reports `aborted: budget` with the counters."""


class Budget:
    def __init__(self, max_calls: int = DEFAULT_MAX_CALLS, max_seconds: float = DEFAULT_MAX_SECONDS,
                 clock=time.monotonic):
        self.max_calls = int(max_calls)
        self.max_seconds = float(max_seconds)
        self._clock = clock
        self._start = clock()
        self.calls = 0

    # --- reading -------------------------------------------------------------------------------
    def elapsed(self) -> float:
        return self._clock() - self._start

    def remaining_calls(self) -> int:
        return max(0, self.max_calls - self.calls)

    def remaining_seconds(self) -> float:
        return max(0.0, self.max_seconds - self.elapsed())

    def exhausted(self) -> bool:
        return self.calls >= self.max_calls or self.elapsed() >= self.max_seconds

    # --- spending ------------------------------------------------------------------------------
    def charge(self, n: int = 1, what: str = "gh") -> None:
        """Spend `n` calls. Raises BudgetExceeded BEFORE the spend when it would cross the cap, or
        when the wall-clock cap has already passed — so the caller never makes the call."""
        if self.elapsed() >= self.max_seconds:
            raise BudgetExceeded(f"time budget exhausted after {self.elapsed():.0f}s ({what})")
        if self.calls + n > self.max_calls:
            raise BudgetExceeded(f"call budget exhausted: {self.calls}+{n} > {self.max_calls} ({what})")
        self.calls += n

    def wrap(self, fn, what: str = "gh"):
        """A callable that charges one unit per invocation, then delegates. Used to wrap `gh` so
        every `gh api …` a stage makes is counted without the stage knowing."""
        def counted(*args, **kwargs):
            self.charge(1, what)
            return fn(*args, **kwargs)
        counted.budget = self  # type: ignore[attr-defined]
        return counted

    def summary(self) -> str:
        return f"gh calls {self.calls}/{self.max_calls} · {self.elapsed():.1f}s/{self.max_seconds:.0f}s"
