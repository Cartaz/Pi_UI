from __future__ import annotations

from pathlib import Path

from controllers.workspace_browser_controller import WorkspaceBrowserController
from controllers.workspace_document_controller import WorkspaceDocumentController
from core.workspace_browser import WorkspaceEntry, WorkspaceEntryKind, WorkspaceScanResult
from core.workspace_document import WorkspaceDocumentResult, WorkspaceDocumentStatus
from ui.adapters.workspace_browser_adapter import WorkspaceBrowserAdapter
from ui.adapters.workspace_document_adapter import WorkspaceDocumentAdapter


class BrowserRunner:
    def __init__(self) -> None:
        self.requests = []

    def submit(self, request_id, root, relative_directory, callback) -> None:
        self.requests.append((request_id, root, relative_directory, callback))

    def cancel_all(self) -> None:
        return


class DocumentRunner:
    def __init__(self) -> None:
        self.requests = []

    def submit(self, request_id, root, relative_path, max_bytes, callback) -> None:
        self.requests.append((request_id, root, relative_path, max_bytes, callback))

    def cancel_all(self) -> None:
        return


def _entry(name: str, kind: WorkspaceEntryKind) -> WorkspaceEntry:
    return WorkspaceEntry(
        name=name,
        relative_path=name,
        kind=kind,
        size_bytes=0,
        modified_ns=0,
        hidden=False,
    )


def test_browser_adapter_emits_leaf_path_but_keeps_directory_activation_in_tree(
    tmp_path: Path,
) -> None:
    runner = BrowserRunner()
    controller = WorkspaceBrowserController(lambda: tmp_path, runner)
    request_id, _root, _relative, callback = runner.requests[0]
    callback(
        request_id,
        WorkspaceScanResult(
            "",
            (
                _entry("docs", WorkspaceEntryKind.DIRECTORY),
                _entry("note.txt", WorkspaceEntryKind.FILE),
            ),
        ),
    )
    adapter = WorkspaceBrowserAdapter(controller)
    activated: list[str] = []
    adapter.leafActivated.connect(activated.append)

    adapter.activateRow(1)
    assert activated == ["note.txt"]

    adapter.activateRow(0)
    assert activated == ["note.txt"]
    assert controller.items[0].expanded
    assert runner.requests[-1][2] == "docs"


def test_document_adapter_exposes_selection_and_exact_text(tmp_path: Path) -> None:
    runner = DocumentRunner()
    controller = WorkspaceDocumentController(lambda: tmp_path, runner)
    adapter = WorkspaceDocumentAdapter(controller)
    selection_changes = 0

    def on_selection_changed() -> None:
        nonlocal selection_changes
        selection_changes += 1

    adapter.selectionChanged.connect(on_selection_changed)
    adapter.openPath("note.txt")

    assert adapter.hasSelection
    assert adapter.selectedPath == "note.txt"
    assert adapter.selectedName == "note.txt"
    assert adapter.loading
    assert selection_changes == 1

    request_id, _root, _path, _max_bytes, callback = runner.requests[0]
    callback(
        request_id,
        WorkspaceDocumentResult(
            relative_path="note.txt",
            status=WorkspaceDocumentStatus.READY,
            text="one\r\ntwo\n",
            size_bytes=9,
        ),
    )

    assert adapter.state == "ready"
    assert adapter.text == "one\r\ntwo\n"
    assert adapter.sizeBytes == 9
    assert adapter.canReload
    assert selection_changes == 1

    adapter.clearDocument()
    assert not adapter.hasSelection
    assert adapter.selectedPath == ""
    assert selection_changes == 2
