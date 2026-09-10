from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from controllers.workspace_browser_controller import WorkspaceBrowserController
from core.workspace_browser import WorkspaceEntry, WorkspaceEntryKind, WorkspaceScanResult, scan_directory


class FakeScanRunner:
    def __init__(self) -> None:
        self.requests: list[tuple[str, Path, str, Callable]] = []
        self.cancel_count = 0

    def submit(self, request_id: str, root: Path, relative_directory: str, callback) -> None:
        self.requests.append((request_id, root, relative_directory, callback))

    def cancel_all(self) -> None:
        self.cancel_count += 1

    def complete(self, index: int, result: WorkspaceScanResult) -> None:
        request_id, _root, _relative, callback = self.requests[index]
        callback(request_id, result)


class ImmediateScanRunner:
    def submit(self, request_id: str, root: Path, relative_directory: str, callback) -> None:
        callback(request_id, scan_directory(root, relative_directory))

    def cancel_all(self) -> None:
        return


def _entry(name: str, kind: WorkspaceEntryKind, relative_path: str | None = None) -> WorkspaceEntry:
    return WorkspaceEntry(
        name=name,
        relative_path=relative_path or name,
        kind=kind,
        size_bytes=0,
        modified_ns=0,
        hidden=name.startswith("."),
    )


def test_root_load_and_directory_expansion_are_lazy(tmp_path: Path) -> None:
    runner = FakeScanRunner()
    root = tmp_path / "workspace"
    root.mkdir()
    current = root
    controller = WorkspaceBrowserController(lambda: current, runner)

    assert controller.loading
    assert [(request[1], request[2]) for request in runner.requests] == [(root, "")]

    runner.complete(
        0,
        WorkspaceScanResult(
            "",
            (
                _entry("docs", WorkspaceEntryKind.DIRECTORY),
                _entry("readme.md", WorkspaceEntryKind.FILE),
            ),
        ),
    )
    assert [item.name for item in controller.items] == ["docs", "readme.md"]
    assert not controller.loading

    controller.toggle_directory(0)
    assert controller.items[0].expanded
    assert controller.items[0].loading
    assert runner.requests[-1][2] == "docs"

    runner.complete(
        1,
        WorkspaceScanResult(
            "docs",
            (_entry("notes.md", WorkspaceEntryKind.FILE, "docs/notes.md"),),
        ),
    )
    assert [(item.name, item.depth) for item in controller.items] == [
        ("docs", 0),
        ("notes.md", 1),
        ("readme.md", 0),
    ]
    assert controller.items[0].expanded
    assert not controller.items[0].loading


def test_collapse_removes_descendants_and_late_result_is_ignored(tmp_path: Path) -> None:
    runner = FakeScanRunner()
    root = tmp_path / "workspace"
    root.mkdir()
    controller = WorkspaceBrowserController(lambda: root, runner)
    runner.complete(0, WorkspaceScanResult("", (_entry("docs", WorkspaceEntryKind.DIRECTORY),)))

    controller.toggle_directory(0)
    controller.toggle_directory(0)
    assert not controller.items[0].expanded

    runner.complete(
        1,
        WorkspaceScanResult(
            "docs",
            (_entry("late.txt", WorkspaceEntryKind.FILE, "docs/late.txt"),),
        ),
    )
    assert [item.name for item in controller.items] == ["docs"]


def test_workspace_switch_invalidates_inflight_results(tmp_path: Path) -> None:
    runner = FakeScanRunner()
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    current = first
    controller = WorkspaceBrowserController(lambda: current, runner)

    current = second
    controller.sync_workspace()
    assert controller.root == second
    assert runner.cancel_count >= 2

    runner.complete(0, WorkspaceScanResult("", (_entry("stale.txt", WorkspaceEntryKind.FILE),)))
    assert controller.items == ()

    runner.complete(1, WorkspaceScanResult("", (_entry("fresh.txt", WorkspaceEntryKind.FILE),)))
    assert [item.name for item in controller.items] == ["fresh.txt"]


def test_refresh_reflects_external_create_and_remove(tmp_path: Path) -> None:
    (tmp_path / "before.txt").write_text("before", encoding="utf-8")
    controller = WorkspaceBrowserController(lambda: tmp_path, ImmediateScanRunner())
    assert [item.name for item in controller.items] == ["before.txt"]

    (tmp_path / "before.txt").unlink()
    (tmp_path / "after.txt").write_text("after", encoding="utf-8")
    controller.refresh()

    assert [item.name for item in controller.items] == ["after.txt"]
    assert controller.last_error is None
