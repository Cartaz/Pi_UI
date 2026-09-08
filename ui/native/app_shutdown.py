"""Application shutdown coordination for the Qt event loop."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from controllers.agent_controller import AgentController, ConnectionState


class AppShutdownCoordinator(QObject):
    """Finish app shutdown only after the owned Pi process has settled.

    ``AgentController.shutdown()`` is intentionally asynchronous. Closing the
    last QML window must therefore not stop the Qt event loop before QProcess
    gets its terminate -> timeout -> kill sequence. A final app-level watchdog
    prevents the desktop process from hanging forever if the native lifecycle
    itself fails to report completion.
    """

    finished = Signal()
    forcedTimeout = Signal(str)

    def __init__(
        self,
        controller: AgentController,
        *,
        timeout_ms: int,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms <= 0:
            raise ValueError("app shutdown timeout must be a positive integer")
        self._controller = controller
        self._timeout_ms = timeout_ms
        self._active = False
        self._done = False

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._force_finish)

    @property
    def active(self) -> bool:
        return self._active and not self._done

    @Slot()
    def request_shutdown(self) -> None:
        if self._done or self._active:
            return
        self._active = True
        self._controller.shutdown()

        if self._controller.connection_state == ConnectionState.STOPPING:
            self._timer.start(self._timeout_ms)
            return
        self._complete()

    @Slot()
    def notify_state_changed(self) -> None:
        if not self.active:
            return
        if self._controller.connection_state != ConnectionState.STOPPING:
            self._complete()

    def _complete(self) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self.finished.emit()

    def _force_finish(self) -> None:
        if not self.active:
            return
        self.forcedTimeout.emit(
            f"Pi shutdown did not settle within {self._timeout_ms} ms; exiting application"
        )
        self._complete()
