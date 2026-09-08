"""Focused QObject adapter for the M0 chat shell."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot

from controllers.agent_controller import AgentController


class AgentAdapter(QObject):
    """Translate QML interaction into typed controller operations."""

    stateChanged = Signal()
    restoreComposerText = Signal(str)

    def __init__(self, controller: AgentController, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._operation_error = ""
        controller.set_state_handler(self._on_controller_state_changed)
        controller.set_recovered_queue_handler(self._on_recovered_queue)

    @Property(str, notify=stateChanged)
    def workspacePath(self) -> str:
        workspace = self._controller.workspace
        return str(workspace) if workspace is not None else ""

    @Property(str, notify=stateChanged)
    def connectionState(self) -> str:
        return str(self._controller.connection_state)

    @Property(str, notify=stateChanged)
    def turnState(self) -> str:
        return str(self._controller.turn_state)

    @Property(str, notify=stateChanged)
    def statusText(self) -> str:
        return self._controller.status_text

    @Property(str, notify=stateChanged)
    def lastError(self) -> str:
        return self._operation_error or self._controller.last_error or ""

    @Property(str, notify=stateChanged)
    def diagnosticTail(self) -> str:
        return self._controller.diagnostic_tail

    @Property(int, notify=stateChanged)
    def selectedProfileIndex(self) -> int:
        return self._controller.selected_profile_index

    @Property(bool, notify=stateChanged)
    def hasWorkspace(self) -> bool:
        return self._controller.workspace is not None

    @Property(bool, notify=stateChanged)
    def canConnect(self) -> bool:
        return self._controller.can_connect

    @Property(bool, notify=stateChanged)
    def canDisconnect(self) -> bool:
        return self._controller.can_disconnect

    @Property(bool, notify=stateChanged)
    def canSend(self) -> bool:
        return self._controller.can_send

    @Property(bool, notify=stateChanged)
    def canStop(self) -> bool:
        return self._controller.can_stop

    @Slot(QUrl, result=bool)
    def setWorkspaceUrl(self, url: QUrl) -> bool:
        if not url.isLocalFile():
            return self._reject("workspace must be a local directory")
        return self._set_workspace(Path(url.toLocalFile()))

    @Slot(str, result=bool)
    def setWorkspacePath(self, path: str) -> bool:
        if not isinstance(path, str) or not path.strip():
            return self._reject("workspace path must not be empty")
        return self._set_workspace(Path(path))

    @Slot(result=bool)
    def refreshProfiles(self) -> bool:
        return self._invoke(self._controller.refresh_profiles)

    @Slot(int, result=bool)
    def selectProfile(self, index: int) -> bool:
        return self._invoke(lambda: self._controller.select_profile(index))

    @Slot(result=bool)
    def connectAgent(self) -> bool:
        return self._invoke(self._controller.connect_agent)

    @Slot(result=bool)
    def disconnectAgent(self) -> bool:
        return self._invoke(self._controller.disconnect_agent)

    @Slot(str, result=bool)
    def sendMessage(self, text: str) -> bool:
        return self._invoke(lambda: self._controller.send_message(text))

    @Slot(result=bool)
    def stopTurn(self) -> bool:
        return self._invoke(self._controller.request_stop)

    def _set_workspace(self, path: Path) -> bool:
        return self._invoke(lambda: self._controller.set_workspace(path))

    def _invoke(self, operation) -> bool:
        try:
            operation()
        except Exception as exc:
            return self._reject(str(exc) or exc.__class__.__name__)
        self._operation_error = ""
        self.stateChanged.emit()
        return True

    def _reject(self, message: str) -> bool:
        self._operation_error = message
        self.stateChanged.emit()
        return False

    def _on_controller_state_changed(self) -> None:
        if self._controller.last_error:
            self._operation_error = ""
        self.stateChanged.emit()

    def _on_recovered_queue(
        self,
        steering: tuple[str, ...],
        follow_up: tuple[str, ...],
    ) -> None:
        restored = "\n".join((*steering, *follow_up))
        if restored:
            self.restoreComposerText.emit(restored)
