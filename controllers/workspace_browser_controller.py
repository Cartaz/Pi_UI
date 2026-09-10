"""Presentation-independent controller for lazy workspace browsing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from core.workspace_browser import WorkspaceEntry, WorkspaceEntryKind, WorkspaceScanResult


class WorkspaceBrowserError(RuntimeError):
    """Raised when a browser action is invalid in the current state."""


@dataclass(frozen=True, slots=True)
class VisibleWorkspaceEntry:
    name: str
    relative_path: str
    kind: WorkspaceEntryKind
    depth: int
    expanded: bool = False
    loading: bool = False
    size_bytes: int = 0
    modified_ns: int = 0
    hidden: bool = False

    @property
    def can_expand(self) -> bool:
        return self.kind == WorkspaceEntryKind.DIRECTORY


ScanCallback = Callable[[str, WorkspaceScanResult], None]
ItemsHandler = Callable[[tuple[VisibleWorkspaceEntry, ...]], None]
StateHandler = Callable[[], None]
WorkspaceProvider = Callable[[], Path | None]


class DirectoryScanRunner(Protocol):
    """Asynchronous boundary used by the browser controller."""

    def submit(
        self,
        request_id: str,
        root: Path,
        relative_directory: str,
        callback: ScanCallback,
    ) -> None: ...

    def cancel_all(self) -> None: ...


class WorkspaceBrowserController:
    """Own the lazy visible-tree projection, never the canonical workspace root."""

    def __init__(
        self,
        workspace_provider: WorkspaceProvider,
        scan_runner: DirectoryScanRunner,
    ) -> None:
        self._workspace_provider = workspace_provider
        self._scan_runner = scan_runner
        self._root: Path | None = None
        self._items: list[VisibleWorkspaceEntry] = []
        self._generation = 0
        self._request_counter = 0
        self._pending: dict[str, str] = {}
        self._status_text = "No workspace selected"
        self._last_error: str | None = None
        self._items_handler: ItemsHandler = lambda _items: None
        self._state_handler: StateHandler = lambda: None
        self.sync_workspace()

    @property
    def root(self) -> Path | None:
        return self._root

    @property
    def items(self) -> tuple[VisibleWorkspaceEntry, ...]:
        return tuple(self._items)

    @property
    def status_text(self) -> str:
        return self._status_text

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def loading(self) -> bool:
        return bool(self._pending)

    def set_items_handler(self, handler: ItemsHandler) -> None:
        self._items_handler = handler

    def set_state_handler(self, handler: StateHandler) -> None:
        self._state_handler = handler

    def sync_workspace(self) -> None:
        """Synchronize derived browser state with the canonical AgentController root."""

        candidate = self._workspace_provider()
        if candidate == self._root:
            return
        self._reset_for_root(candidate)

    def refresh(self) -> None:
        """Reload the selected root and collapse all expanded directories."""

        candidate = self._workspace_provider()
        if candidate != self._root:
            self._reset_for_root(candidate)
            return
        if self._root is None:
            return
        self._generation += 1
        self._scan_runner.cancel_all()
        self._pending.clear()
        self._items.clear()
        self._last_error = None
        self._status_text = "Refreshing workspace"
        self._emit_items()
        self._emit_state()
        self._request_scan("")

    def toggle_directory(self, index: int) -> None:
        if not 0 <= index < len(self._items):
            raise WorkspaceBrowserError("workspace row index is out of range")
        item = self._items[index]
        if not item.can_expand:
            return

        if item.expanded:
            self._collapse(index)
            return

        self._items[index] = replace(item, expanded=True, loading=True)
        self._last_error = None
        self._status_text = f"Loading {item.name}"
        self._emit_items()
        self._emit_state()
        self._request_scan(item.relative_path)

    def cancel(self) -> None:
        self._generation += 1
        self._pending.clear()
        self._scan_runner.cancel_all()
        if self._items:
            self._items = [replace(item, loading=False) for item in self._items]
            self._emit_items()
        self._emit_state()

    def _reset_for_root(self, root: Path | None) -> None:
        self._generation += 1
        self._scan_runner.cancel_all()
        self._pending.clear()
        self._items.clear()
        self._root = root
        self._last_error = None
        if root is None:
            self._status_text = "No workspace selected"
            self._emit_items()
            self._emit_state()
            return
        self._status_text = "Loading workspace"
        self._emit_items()
        self._emit_state()
        self._request_scan("")

    def _collapse(self, index: int) -> None:
        item = self._items[index]
        self._pending.pop(item.relative_path, None)
        self._items[index] = replace(item, expanded=False, loading=False)
        depth = item.depth
        end = index + 1
        while end < len(self._items) and self._items[end].depth > depth:
            self._pending.pop(self._items[end].relative_path, None)
            end += 1
        del self._items[index + 1 : end]
        self._status_text = "Workspace ready"
        self._emit_items()
        self._emit_state()

    def _request_scan(self, relative_directory: str) -> None:
        root = self._root
        if root is None:
            return
        self._request_counter += 1
        request_id = f"{self._generation}:{self._request_counter}"
        self._pending[relative_directory] = request_id
        try:
            self._scan_runner.submit(
                request_id,
                root,
                relative_directory,
                self._on_scan_result,
            )
        except Exception as exc:
            self._pending.pop(relative_directory, None)
            self._handle_scan_error(relative_directory, str(exc))

    def _on_scan_result(self, request_id: str, result: WorkspaceScanResult) -> None:
        expected = self._pending.get(result.relative_directory)
        if expected != request_id:
            return
        self._pending.pop(result.relative_directory, None)

        if result.error:
            self._handle_scan_error(result.relative_directory, result.error)
            return

        if result.relative_directory == "":
            self._items = [self._visible(entry, depth=0) for entry in result.entries]
            self._status_text = f"{len(self._items)} workspace items"
            self._last_error = None
            self._emit_items()
            self._emit_state()
            return

        parent_index = self._find_index(result.relative_directory)
        if parent_index is None:
            return
        parent = self._items[parent_index]
        if not parent.expanded:
            return

        self._items[parent_index] = replace(parent, loading=False)
        children = [self._visible(entry, depth=parent.depth + 1) for entry in result.entries]
        self._items[parent_index + 1 : parent_index + 1] = children
        self._last_error = None
        self._status_text = "Workspace ready"
        self._emit_items()
        self._emit_state()

    def _handle_scan_error(self, relative_directory: str, message: str) -> None:
        self._last_error = message
        if relative_directory:
            index = self._find_index(relative_directory)
            if index is not None:
                item = self._items[index]
                self._items[index] = replace(item, expanded=False, loading=False)
        self._status_text = "Workspace scan failed"
        self._emit_items()
        self._emit_state()

    def _find_index(self, relative_path: str) -> int | None:
        for index, item in enumerate(self._items):
            if item.relative_path == relative_path:
                return index
        return None

    @staticmethod
    def _visible(entry: WorkspaceEntry, *, depth: int) -> VisibleWorkspaceEntry:
        return VisibleWorkspaceEntry(
            name=entry.name,
            relative_path=entry.relative_path,
            kind=entry.kind,
            depth=depth,
            size_bytes=entry.size_bytes,
            modified_ns=entry.modified_ns,
            hidden=entry.hidden,
        )

    def _emit_items(self) -> None:
        self._items_handler(tuple(self._items))

    def _emit_state(self) -> None:
        self._state_handler()
