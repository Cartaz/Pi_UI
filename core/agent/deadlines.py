"""Small scheduling contract for AgentClient deadlines.

The core client owns *what* expires; the UI/native layer owns the event-loop
mechanism used to schedule callbacks. This keeps Qt timers out of core while
ensuring callbacks still execute on the GUI thread in the desktop app.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

DeadlineCallback = Callable[[], None]


class DeadlineHandle(Protocol):
    """Cancellable one-shot deadline."""

    def cancel(self) -> None: ...


class DeadlineScheduler(Protocol):
    """Schedule a callback after a positive millisecond delay."""

    def call_later(self, delay_ms: int, callback: DeadlineCallback) -> DeadlineHandle: ...
