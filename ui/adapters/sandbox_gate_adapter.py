"""Focused QObject adapter for the explicit Bubblewrap confinement gate."""

from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal, Slot

from controllers.sandbox_gate_controller import SandboxGateController


class SandboxGateAdapter(QObject):
    stateChanged = Signal()

    def __init__(
        self,
        controller: SandboxGateController,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._operation_error = ""
        controller.set_state_handler(self._on_state_changed)

    @Property(bool, notify=stateChanged)
    def running(self) -> bool:
        return self._controller.running

    @Property(bool, notify=stateChanged)
    def canRun(self) -> bool:
        return self._controller.can_run

    @Property(str, notify=stateChanged)
    def statusText(self) -> str:
        return self._controller.status_text

    @Property(str, notify=stateChanged)
    def operationError(self) -> str:
        return self._operation_error

    @Property(int, notify=stateChanged)
    def failCount(self) -> int:
        return self._controller.fail_count

    @Property(int, notify=stateChanged)
    def passCount(self) -> int:
        return self._controller.pass_count

    @Property(str, notify=stateChanged)
    def sanitizedManifest(self) -> str:
        return self._controller.manifest

    @Slot(result=bool)
    def runGate(self) -> bool:
        return self._invoke(self._controller.run)

    @Slot(result=bool)
    def cancelGate(self) -> bool:
        return self._invoke(self._controller.cancel)

    def _invoke(self, operation) -> bool:
        try:
            operation()
        except Exception as exc:
            self._operation_error = str(exc) or exc.__class__.__name__
            self.stateChanged.emit()
            return False
        self._operation_error = ""
        self.stateChanged.emit()
        return True

    def _on_state_changed(self) -> None:
        self._operation_error = ""
        self.stateChanged.emit()
