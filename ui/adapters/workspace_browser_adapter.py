"""Focused QObject adapter for the read-only workspace browser."""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot

from controllers.workspace_browser_controller import (
    WorkspaceBrowserController,
    WorkspaceBrowserError,
)


class WorkspaceBrowserAdapter(QObject):
    stateChanged = Signal()

    def __init__(self, controller: WorkspaceBrowserController) -> None:
        super().__init__()
        self._controller = controller
        self._operation_error = ""
        controller.set_state_handler(self._on_controller_state)

    @Property(bool, notify=stateChanged)
    def hasWorkspace(self) -> bool:  # noqa: N802
        return self._controller.root is not None

    @Property(bool, notify=stateChanged)
    def loading(self) -> bool:
        return self._controller.loading

    @Property(str, notify=stateChanged)
    def statusText(self) -> str:  # noqa: N802
        return self._controller.status_text

    @Property(str, notify=stateChanged)
    def lastError(self) -> str:  # noqa: N802
        return self._controller.last_error or ""

    @Property(str, notify=stateChanged)
    def operationError(self) -> str:  # noqa: N802
        return self._operation_error

    @Property(int, notify=stateChanged)
    def itemCount(self) -> int:  # noqa: N802
        return len(self._controller.items)

    @Slot()
    def refresh(self) -> None:
        self._operation_error = ""
        try:
            self._controller.refresh()
        except Exception as exc:
            self._operation_error = str(exc)
            self.stateChanged.emit()

    @Slot(int)
    def toggleRow(self, index: int) -> None:  # noqa: N802
        self._operation_error = ""
        try:
            self._controller.toggle_directory(index)
        except WorkspaceBrowserError as exc:
            self._operation_error = str(exc)
            self.stateChanged.emit()

    def _on_controller_state(self) -> None:
        self.stateChanged.emit()
