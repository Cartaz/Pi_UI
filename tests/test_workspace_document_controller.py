from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from controllers.workspace_document_controller import (
    WorkspaceDocumentController,
    WorkspaceDocumentState,
)
from core.workspace_document import WorkspaceDocumentResult, WorkspaceDocumentStatus, load_document_preview


class FakeDocumentRunner:
    def __init__(self) -> None:
        self.requests: list[tuple[str, Path, str, int, Callable]] = []
        self.cancel_count = 0

    def submit(self, request_id, root, relative_path, max_bytes, callback) -> None:
        self.requests.append((request_id, root, relative_path, max_bytes, callback))

    def cancel_all(self) -> None:
        self.cancel_count += 1

    def complete(self, index: int, result: WorkspaceDocumentResult) -> None:
        request_id, _root, _path, _max_bytes, callback = self.requests[index]
        callback(request_id, result)


class ImmediateDocumentRunner:
    def submit(self, request_id, root, relative_path, max_bytes, callback) -> None:
        callback(
            request_id,
            load_document_preview(root, relative_path, max_bytes=max_bytes),
        )

    def cancel_all(self) -> None:
        return


def test_open_path_projects_async_result_without_owning_workspace(tmp_path: Path) -> None:
    runner = FakeDocumentRunner()
    controller = WorkspaceDocumentController(lambda: tmp_path, runner, max_preview_bytes=4096)

    controller.open_path("docs/note.md")

    assert controller.root == tmp_path
    assert controller.state == WorkspaceDocumentState.LOADING
    assert controller.selected_path == "docs/note.md"
    assert controller.selected_name == "note.md"
    assert runner.requests[-1][1:4] == (tmp_path, "docs/note.md", 4096)

    runner.complete(
        0,
        WorkspaceDocumentResult(
            relative_path="docs/note.md",
            status=WorkspaceDocumentStatus.READY,
            text="hello\r\nworld",
            size_bytes=12,
        ),
    )

    assert controller.state == WorkspaceDocumentState.READY
    assert controller.text == "hello\r\nworld"
    assert controller.size_bytes == 12
    assert controller.can_reload


def test_workspace_switch_clears_selection_and_ignores_late_result(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    current = first
    runner = FakeDocumentRunner()
    controller = WorkspaceDocumentController(lambda: current, runner)

    controller.open_path("stale.txt")
    current = second
    controller.sync_workspace()

    assert controller.root == second
    assert controller.state == WorkspaceDocumentState.IDLE
    assert controller.selected_path == ""
    assert controller.text == ""

    runner.complete(
        0,
        WorkspaceDocumentResult(
            relative_path="stale.txt",
            status=WorkspaceDocumentStatus.READY,
            text="stale",
            size_bytes=5,
        ),
    )
    assert controller.text == ""
    assert controller.state == WorkspaceDocumentState.IDLE


def test_reload_reflects_external_file_change(tmp_path: Path) -> None:
    note = tmp_path / "note.txt"
    note.write_text("before", encoding="utf-8")
    controller = WorkspaceDocumentController(lambda: tmp_path, ImmediateDocumentRunner())

    controller.open_path("note.txt")
    assert controller.text == "before"

    note.write_text("after", encoding="utf-8")
    controller.reload()

    assert controller.state == WorkspaceDocumentState.READY
    assert controller.text == "after"


def test_unsupported_result_clears_text_and_keeps_selection(tmp_path: Path) -> None:
    runner = FakeDocumentRunner()
    controller = WorkspaceDocumentController(lambda: tmp_path, runner)
    controller.open_path("archive.bin")

    runner.complete(
        0,
        WorkspaceDocumentResult(
            relative_path="archive.bin",
            status=WorkspaceDocumentStatus.UNSUPPORTED,
            message="Binary-looking files are not previewed",
            size_bytes=100,
        ),
    )

    assert controller.state == WorkspaceDocumentState.UNSUPPORTED
    assert controller.selected_path == "archive.bin"
    assert controller.text == ""
    assert controller.message == "Binary-looking files are not previewed"
    assert controller.can_reload


def test_without_workspace_starts_idle_and_cannot_open() -> None:
    runner = FakeDocumentRunner()
    controller = WorkspaceDocumentController(lambda: None, runner)

    assert controller.status_text == "No workspace selected"
    assert not controller.has_selection
    assert not controller.can_reload
