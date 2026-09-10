from __future__ import annotations

import os
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.workspace_document import WorkspaceDocumentResult, WorkspaceDocumentStatus
from ui.native.workspace_document_runner import QtDocumentLoadRunner


def _application() -> QApplication:
    instance = QApplication.instance()
    if instance is not None:
        return instance
    return QApplication([])


def _wait_until(app: QApplication, predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert predicate()


def test_document_load_runs_off_gui_thread_and_callback_returns_on_gui_thread(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _application()
    main_thread = threading.get_ident()
    worker_threads: list[int] = []
    callback_threads: list[int] = []
    results: list[WorkspaceDocumentResult] = []

    def fake_load(root: Path, relative_path: str, *, max_bytes: int, cancelled):
        worker_threads.append(threading.get_ident())
        return WorkspaceDocumentResult(
            relative_path=relative_path,
            status=WorkspaceDocumentStatus.READY,
            text="ok",
            size_bytes=2,
        )

    monkeypatch.setattr("ui.native.workspace_document_runner.load_document_preview", fake_load)
    runner = QtDocumentLoadRunner(app)
    runner.submit(
        "doc-1",
        tmp_path,
        "note.txt",
        4096,
        lambda _request_id, result: (
            callback_threads.append(threading.get_ident()),
            results.append(result),
        ),
    )

    _wait_until(app, lambda: bool(results))
    assert worker_threads and worker_threads[0] != main_thread
    assert callback_threads == [main_thread]
    assert results[0].text == "ok"
    runner.shutdown()


def test_cancel_all_suppresses_late_document_callback(tmp_path: Path, monkeypatch) -> None:
    app = _application()
    started = threading.Event()
    release = threading.Event()
    callbacks: list[WorkspaceDocumentResult] = []

    def blocked_load(root: Path, relative_path: str, *, max_bytes: int, cancelled):
        started.set()
        release.wait(timeout=2.0)
        return WorkspaceDocumentResult(
            relative_path=relative_path,
            status=WorkspaceDocumentStatus.READY,
            text="late",
            size_bytes=4,
        )

    monkeypatch.setattr("ui.native.workspace_document_runner.load_document_preview", blocked_load)
    runner = QtDocumentLoadRunner(app)
    runner.submit(
        "doc-1",
        tmp_path,
        "note.txt",
        4096,
        lambda _request_id, result: callbacks.append(result),
    )

    _wait_until(app, started.is_set)
    runner.cancel_all()
    release.set()
    deadline = time.monotonic() + 0.1
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)

    assert callbacks == []
    runner.shutdown()
