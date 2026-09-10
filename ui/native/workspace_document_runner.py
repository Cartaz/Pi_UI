"""Qt thread-pool boundary for non-blocking workspace document previews."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from core.workspace_document import WorkspaceDocumentResult, load_document_preview

DocumentCallback = Callable[[str, WorkspaceDocumentResult], None]


class _DocumentLoadTask(QRunnable):
    def __init__(
        self,
        owner: "QtDocumentLoadRunner",
        request_id: str,
        root: Path,
        relative_path: str,
        max_bytes: int,
        cancelled: Event,
    ) -> None:
        super().__init__()
        self._owner = owner
        self._request_id = request_id
        self._root = root
        self._relative_path = relative_path
        self._max_bytes = max_bytes
        self._cancelled = cancelled

    def run(self) -> None:
        result = load_document_preview(
            self._root,
            self._relative_path,
            max_bytes=self._max_bytes,
            cancelled=self._cancelled.is_set,
        )
        if not self._cancelled.is_set():
            self._owner._loadFinished.emit(self._request_id, result)


class QtDocumentLoadRunner(QObject):
    """Load previews off the GUI thread and marshal results back to Qt."""

    _loadFinished = Signal(str, object)

    def __init__(self, parent: QObject | None = None, *, max_threads: int = 2) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max_threads)
        self._callbacks: dict[str, DocumentCallback] = {}
        self._cancel_tokens: dict[str, Event] = {}
        self._closed = False
        self._loadFinished.connect(self._deliver)

    def submit(
        self,
        request_id: str,
        root: Path,
        relative_path: str,
        max_bytes: int,
        callback: DocumentCallback,
    ) -> None:
        if self._closed:
            raise RuntimeError("workspace document runner is shut down")
        if request_id in self._callbacks:
            raise RuntimeError(f"duplicate workspace document request: {request_id}")

        cancelled = Event()
        self._callbacks[request_id] = callback
        self._cancel_tokens[request_id] = cancelled
        self._pool.start(
            _DocumentLoadTask(
                self,
                request_id,
                root,
                relative_path,
                max_bytes,
                cancelled,
            )
        )

    def cancel_all(self) -> None:
        for token in self._cancel_tokens.values():
            token.set()
        self._callbacks.clear()
        self._cancel_tokens.clear()
        self._pool.clear()

    @Slot(str, object)
    def _deliver(self, request_id: str, result: WorkspaceDocumentResult) -> None:
        callback = self._callbacks.pop(request_id, None)
        self._cancel_tokens.pop(request_id, None)
        if callback is not None and not self._closed:
            callback(request_id, result)

    @Slot()
    def shutdown(self) -> None:
        self._closed = True
        self.cancel_all()
