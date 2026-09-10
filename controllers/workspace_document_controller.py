"""Presentation-independent controller for one read-only workspace document preview."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Protocol

from core.workspace_document import (
    MAX_PREVIEW_BYTES,
    WorkspaceDocumentResult,
    WorkspaceDocumentStatus,
)


class WorkspaceDocumentError(RuntimeError):
    """Raised when a document action is invalid in the current state."""


class WorkspaceDocumentState(StrEnum):
    IDLE = "idle"
    LOADING = "loading"
    READY = "ready"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


DocumentCallback = Callable[[str, WorkspaceDocumentResult], None]
StateHandler = Callable[[], None]
WorkspaceProvider = Callable[[], Path | None]


class DocumentLoadRunner(Protocol):
    """Asynchronous boundary used by the document controller."""

    def submit(
        self,
        request_id: str,
        root: Path,
        relative_path: str,
        max_bytes: int,
        callback: DocumentCallback,
    ) -> None: ...

    def cancel_all(self) -> None: ...


class WorkspaceDocumentController:
    """Own transient selected-document state derived from the canonical workspace."""

    def __init__(
        self,
        workspace_provider: WorkspaceProvider,
        load_runner: DocumentLoadRunner,
        *,
        max_preview_bytes: int = MAX_PREVIEW_BYTES,
    ) -> None:
        if max_preview_bytes <= 0:
            raise ValueError("max_preview_bytes must be positive")
        self._workspace_provider = workspace_provider
        self._load_runner = load_runner
        self._max_preview_bytes = max_preview_bytes
        self._root: Path | None = None
        self._state = WorkspaceDocumentState.IDLE
        self._selected_path = ""
        self._text = ""
        self._message = ""
        self._size_bytes = 0
        self._status_text = "No workspace selected"
        self._generation = 0
        self._request_counter = 0
        self._pending_request_id: str | None = None
        self._state_handler: StateHandler = lambda: None
        self.sync_workspace()

    @property
    def root(self) -> Path | None:
        return self._root

    @property
    def state(self) -> WorkspaceDocumentState:
        return self._state

    @property
    def selected_path(self) -> str:
        return self._selected_path

    @property
    def selected_name(self) -> str:
        return PurePosixPath(self._selected_path).name if self._selected_path else ""

    @property
    def text(self) -> str:
        return self._text

    @property
    def message(self) -> str:
        return self._message

    @property
    def size_bytes(self) -> int:
        return self._size_bytes

    @property
    def status_text(self) -> str:
        return self._status_text

    @property
    def loading(self) -> bool:
        return self._state == WorkspaceDocumentState.LOADING

    @property
    def has_selection(self) -> bool:
        return bool(self._selected_path)

    @property
    def can_reload(self) -> bool:
        return self._root is not None and self.has_selection and not self.loading

    @property
    def max_preview_bytes(self) -> int:
        return self._max_preview_bytes

    def set_state_handler(self, handler: StateHandler) -> None:
        self._state_handler = handler

    def sync_workspace(self) -> None:
        candidate = self._workspace_provider()
        if candidate == self._root:
            return
        self._root = candidate
        self._clear_state(cancel=True)

    def open_path(self, relative_path: str) -> None:
        candidate = self._workspace_provider()
        if candidate != self._root:
            self._root = candidate
            self._clear_state(cancel=True)
        if self._root is None:
            raise WorkspaceDocumentError("no workspace is selected")

        self._start_load(relative_path)

    def reload(self) -> None:
        if self._root is None:
            raise WorkspaceDocumentError("no workspace is selected")
        if not self._selected_path:
            raise WorkspaceDocumentError("no document is selected")
        self._start_load(self._selected_path)

    def clear(self) -> None:
        self._clear_state(cancel=True)

    def cancel(self) -> None:
        self._generation += 1
        self._pending_request_id = None
        self._load_runner.cancel_all()

    def _start_load(self, relative_path: str) -> None:
        root = self._root
        if root is None:
            raise WorkspaceDocumentError("no workspace is selected")

        self._generation += 1
        self._load_runner.cancel_all()
        self._request_counter += 1
        request_id = f"{self._generation}:{self._request_counter}"
        self._pending_request_id = request_id
        self._selected_path = relative_path
        self._text = ""
        self._message = ""
        self._size_bytes = 0
        self._state = WorkspaceDocumentState.LOADING
        self._status_text = f"Loading {self.selected_name or 'document'}"
        self._emit_state()

        try:
            self._load_runner.submit(
                request_id,
                root,
                relative_path,
                self._max_preview_bytes,
                self._on_load_result,
            )
        except Exception as exc:
            if self._pending_request_id == request_id:
                self._pending_request_id = None
                self._state = WorkspaceDocumentState.ERROR
                self._message = str(exc)
                self._status_text = "Document preview failed"
                self._emit_state()

    def _on_load_result(self, request_id: str, result: WorkspaceDocumentResult) -> None:
        if request_id != self._pending_request_id:
            return
        self._pending_request_id = None
        if result.relative_path != self._selected_path:
            return
        if result.status == WorkspaceDocumentStatus.CANCELLED:
            return

        self._size_bytes = result.size_bytes
        self._message = result.message
        if result.status == WorkspaceDocumentStatus.READY:
            self._state = WorkspaceDocumentState.READY
            self._text = result.text
            self._status_text = f"Preview ready · {result.size_bytes} bytes"
        elif result.status == WorkspaceDocumentStatus.UNSUPPORTED:
            self._state = WorkspaceDocumentState.UNSUPPORTED
            self._text = ""
            self._status_text = "Preview unavailable"
        else:
            self._state = WorkspaceDocumentState.ERROR
            self._text = ""
            self._status_text = "Document preview failed"
        self._emit_state()

    def _clear_state(self, *, cancel: bool) -> None:
        if cancel:
            self._generation += 1
            self._pending_request_id = None
            self._load_runner.cancel_all()
        self._selected_path = ""
        self._text = ""
        self._message = ""
        self._size_bytes = 0
        self._state = WorkspaceDocumentState.IDLE
        self._status_text = "No document selected" if self._root is not None else "No workspace selected"
        self._emit_state()

    def _emit_state(self) -> None:
        self._state_handler()
