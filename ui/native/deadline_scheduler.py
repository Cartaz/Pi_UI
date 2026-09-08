"""Qt event-loop implementation of the agent deadline scheduler."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer

from core.agent.deadlines import DeadlineCallback, DeadlineHandle


class QtDeadlineHandle:
    """Own one QTimer and make cancellation idempotent."""

    def __init__(self, timer: QTimer) -> None:
        self._timer: QTimer | None = timer

    def cancel(self) -> None:
        timer = self._timer
        if timer is None:
            return
        self._timer = None
        timer.stop()
        timer.deleteLater()


class QtDeadlineScheduler(QObject):
    """Create one-shot deadlines that run on the owning Qt thread."""

    def call_later(self, delay_ms: int, callback: DeadlineCallback) -> DeadlineHandle:
        if not isinstance(delay_ms, int) or isinstance(delay_ms, bool) or delay_ms <= 0:
            raise ValueError("deadline delay must be a positive integer")
        if not callable(callback):
            raise TypeError("deadline callback must be callable")

        timer = QTimer(self)
        timer.setSingleShot(True)
        handle = QtDeadlineHandle(timer)

        def fire() -> None:
            handle.cancel()
            callback()

        timer.timeout.connect(fire)
        timer.start(delay_ms)
        return handle
