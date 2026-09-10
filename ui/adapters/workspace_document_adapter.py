"""Focused QObject adapter for one read-only workspace document preview."""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot

from controllers.workspace_document_controller import (
    WorkspaceDocumentController,
    WorkspaceDocumentError,
)


class WorkspaceDocumentAdapter(QObject):
    stateChanged = Signal()
    selectionChanged = Signal()

    def __init__(self, controller: WorkspaceDocumentController) -> None:
        super().__init__()
        self._controller = controller
        self._operation_error = ""
        self._last_selected_path = controller.selected_path
        controller.set_state_handler(self._on_controller_state)

    @Property(str, notify=stateChanged)
    def state(self) -> str:
        return str(self._controller.state)

    @Property(bool, notify=stateChanged)
    def loading(self) -> bool:
        return self._controller.loading

    @Property(bool, notify=selectionChanged)
    def hasSelection(self) -> bool:  # noqa: N802
        return self._controller.has_selection

    @Property(bool, notify=stateChanged)
    def canReload(self) -> bool:  # noqa: N802
        return self._controller.can_reload

    @Property(str, notify=selectionChanged)
    def selectedPath(self) -> str:  # noqa: N802
        return self._controller.selected_path

    @Property(str, notify=selectionChanged)
    def selectedName(self) -> str:  # noqa: N802
        return self._controller.selected_name

    @Property(str, notify=stateChanged)
    def text(self) -> str:
        return self._controller.text

    @Property(str, notify=stateChanged)
    def message(self) -> str:
        return self._controller.message

    @Property(str, notify=stateChanged)
    def statusText(self) -> str:  # noqa: N802
        return self._controller.status_text

    @Property(str, notify=stateChanged)
    def operationError(self) -> str:  # noqa: N802
        return self._operation_error

    @Property(int, notify=stateChanged)
    def sizeBytes(self) -> int:  # noqa: N802
        return self._controller.size_bytes

    @Property(int, constant=True)
    def maxPreviewBytes(self) -> int:  # noqa: N802
        return self._controller.max_preview_bytes

    @Slot(str)
    def openPath(self, relative_path: str) -> None:  # noqa: N802
        self._operation_error = ""
        try:
            self._controller.open_path(relative_path)
        except WorkspaceDocumentError as exc:
            self._operation_error = str(exc)
            self.stateChanged.emit()

    @Slot()
    def reload(self) -> None:
        self._operation_error = ""
        try:
            self._controller.reload()
        except WorkspaceDocumentError as exc:
            self._operation_error = str(exc)
            self.stateChanged.emit()

    @Slot()
    def clearDocument(self) -> None:  # noqa: N802
        self._operation_error = ""
        self._controller.clear()

    def _on_controller_state(self) -> None:
        selected_path = self._controller.selected_path
        if selected_path != self._last_selected_path:
            self._last_selected_path = selected_path
            self.selectionChanged.emit()
        self.stateChanged.emit()
