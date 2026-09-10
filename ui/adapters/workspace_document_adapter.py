"""Focused QObject adapter for one read-only workspace document preview."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Property, QObject, Signal, Slot

from controllers.workspace_document_controller import (
    WorkspaceDocumentController,
    WorkspaceDocumentError,
)
from ui.text_projection import (
    TextSelectionError,
    exact_source_selection,
    qt_plain_text_projection,
)

CopyText = Callable[[str], None]


class WorkspaceDocumentAdapter(QObject):
    stateChanged = Signal()
    selectionChanged = Signal()

    def __init__(
        self,
        controller: WorkspaceDocumentController,
        copy_text: CopyText | None = None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._copy_text = copy_text
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
        """Canonical decoded source text, including original newline sequences."""

        return self._controller.text

    @Property(str, notify=stateChanged)
    def renderedText(self) -> str:  # noqa: N802
        """QTextDocument-compatible projection used only for visual rendering."""

        return qt_plain_text_projection(self._controller.text)

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

    @Slot(int, int, result=bool)
    def copySelection(self, start_utf16: int, end_utf16: int) -> bool:  # noqa: N802
        """Copy a rendered Qt selection using the exact canonical source slice."""

        self._operation_error = ""
        if start_utf16 == end_utf16:
            return False
        if self._copy_text is None:
            self._operation_error = "clipboard integration is unavailable"
            self.stateChanged.emit()
            return False
        try:
            selected = exact_source_selection(
                self._controller.text,
                start_utf16,
                end_utf16,
            )
            self._copy_text(selected)
        except (TextSelectionError, RuntimeError, OSError) as exc:
            self._operation_error = str(exc)
            self.stateChanged.emit()
            return False
        return True

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
