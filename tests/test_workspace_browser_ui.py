from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from controllers.workspace_browser_controller import WorkspaceBrowserController
from core.workspace_browser import WorkspaceEntry, WorkspaceEntryKind, WorkspaceScanResult
from ui.adapters.workspace_browser_adapter import WorkspaceBrowserAdapter
from ui.models.workspace_tree_model import WorkspaceTreeListModel


class FakeRunner:
    def __init__(self) -> None:
        self.requests = []

    def submit(self, request_id, root, relative_directory, callback) -> None:
        self.requests.append((request_id, root, relative_directory, callback))

    def cancel_all(self) -> None:
        return

    def complete(self, index: int, result: WorkspaceScanResult) -> None:
        request_id, _root, _relative, callback = self.requests[index]
        callback(request_id, result)


def _application() -> QApplication:
    instance = QApplication.instance()
    if instance is not None:
        return instance
    return QApplication([])


def _entry(name: str, kind: WorkspaceEntryKind) -> WorkspaceEntry:
    return WorkspaceEntry(
        name=name,
        relative_path=name,
        kind=kind,
        size_bytes=12,
        modified_ns=123,
        hidden=False,
    )


def test_model_roles_and_adapter_toggle_are_wired(tmp_path: Path) -> None:
    _application()
    runner = FakeRunner()
    controller = WorkspaceBrowserController(lambda: tmp_path, runner)
    model = WorkspaceTreeListModel(controller)
    adapter = WorkspaceBrowserAdapter(controller)

    runner.complete(
        0,
        WorkspaceScanResult(
            "",
            (
                _entry("docs", WorkspaceEntryKind.DIRECTORY),
                _entry("note.md", WorkspaceEntryKind.FILE),
            ),
        ),
    )

    assert model.rowCount() == 2
    roles = {bytes(name).decode(): role for role, name in model.roleNames().items()}
    first = model.index(0, 0)
    second = model.index(1, 0)
    assert model.data(first, roles["name"]) == "docs"
    assert model.data(first, roles["entryKind"]) == "directory"
    assert model.data(first, roles["canExpand"]) is True
    assert model.data(first, roles["depth"]) == 0
    assert model.data(second, Qt.ItemDataRole.DisplayRole) == "note.md"
    assert adapter.hasWorkspace
    assert adapter.itemCount == 2

    adapter.toggleRow(0)
    assert len(runner.requests) == 2
    assert runner.requests[1][2] == "docs"


def test_adapter_refresh_is_safe_without_workspace() -> None:
    _application()
    runner = FakeRunner()
    controller = WorkspaceBrowserController(lambda: None, runner)
    adapter = WorkspaceBrowserAdapter(controller)

    adapter.refresh()

    assert not adapter.hasWorkspace
    assert adapter.itemCount == 0
    assert adapter.operationError == ""
