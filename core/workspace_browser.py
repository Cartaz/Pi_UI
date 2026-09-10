"""Confined, read-only directory scanning for the AIOS workspace browser."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class WorkspaceBrowseError(RuntimeError):
    """Raised when a workspace path cannot be browsed safely."""


class WorkspaceEntryKind(StrEnum):
    DIRECTORY = "directory"
    FILE = "file"
    SYMLINK = "symlink"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class WorkspaceEntry:
    """Presentation-neutral metadata for one direct child of a directory."""

    name: str
    relative_path: str
    kind: WorkspaceEntryKind
    size_bytes: int
    modified_ns: int
    hidden: bool

    @property
    def can_expand(self) -> bool:
        return self.kind == WorkspaceEntryKind.DIRECTORY


@dataclass(frozen=True, slots=True)
class WorkspaceScanResult:
    relative_directory: str
    entries: tuple[WorkspaceEntry, ...]
    error: str | None = None


CancelCheck = Callable[[], bool]


def scan_directory(
    root: Path,
    relative_directory: str = "",
    *,
    cancelled: CancelCheck | None = None,
) -> WorkspaceScanResult:
    """Scan one directory without recursively traversing the workspace.

    ``relative_directory`` must name a real directory below ``root``. Symlink
    components are rejected even when their targets remain inside the root;
    symlink entries are deliberately leaf nodes in the first M1 browser slice.
    This keeps host-side browsing aligned with the sandbox's confinement goal
    and prevents an external symlink target from becoming visible through the
    GUI.
    """

    try:
        root_resolved = root.expanduser().resolve(strict=True)
    except OSError as exc:
        return WorkspaceScanResult(relative_directory, (), f"workspace unavailable: {exc}")
    if not root_resolved.is_dir():
        return WorkspaceScanResult(relative_directory, (), "workspace root is not a directory")

    try:
        directory = _resolve_child_directory(root_resolved, relative_directory)
    except WorkspaceBrowseError as exc:
        return WorkspaceScanResult(relative_directory, (), str(exc))

    entries: list[WorkspaceEntry] = []
    try:
        with os.scandir(directory) as iterator:
            for item in iterator:
                if cancelled is not None and cancelled():
                    return WorkspaceScanResult(relative_directory, ())
                entries.append(_entry_from_dirent(root_resolved, item))
    except OSError as exc:
        return WorkspaceScanResult(relative_directory, (), f"cannot read directory: {exc}")

    entries.sort(key=_entry_sort_key)
    return WorkspaceScanResult(relative_directory, tuple(entries))


def _resolve_child_directory(root: Path, relative_directory: str) -> Path:
    relative = Path(relative_directory)
    if relative.is_absolute():
        raise WorkspaceBrowseError("absolute browser paths are not allowed")

    parts = tuple(part for part in relative.parts if part not in {"", "."})
    if any(part == ".." for part in parts):
        raise WorkspaceBrowseError("parent traversal is not allowed")

    candidate = root
    for part in parts:
        candidate = candidate / part
        try:
            if candidate.is_symlink():
                raise WorkspaceBrowseError("symlink directories are not traversable")
        except OSError as exc:
            raise WorkspaceBrowseError(f"cannot inspect directory path: {exc}") from exc

    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise WorkspaceBrowseError(f"directory unavailable: {exc}") from exc

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise WorkspaceBrowseError("directory escapes workspace root") from exc
    if not resolved.is_dir():
        raise WorkspaceBrowseError("browser path is not a directory")
    return resolved


def _entry_from_dirent(root: Path, item: os.DirEntry[str]) -> WorkspaceEntry:
    path = Path(item.path)
    relative_path = path.relative_to(root).as_posix()
    try:
        if item.is_symlink():
            kind = WorkspaceEntryKind.SYMLINK
        elif item.is_dir(follow_symlinks=False):
            kind = WorkspaceEntryKind.DIRECTORY
        elif item.is_file(follow_symlinks=False):
            kind = WorkspaceEntryKind.FILE
        else:
            kind = WorkspaceEntryKind.OTHER
        stat_result = item.stat(follow_symlinks=False)
        size_bytes = stat_result.st_size if kind == WorkspaceEntryKind.FILE else 0
        modified_ns = stat_result.st_mtime_ns
    except OSError:
        kind = WorkspaceEntryKind.OTHER
        size_bytes = 0
        modified_ns = 0

    return WorkspaceEntry(
        name=item.name,
        relative_path=relative_path,
        kind=kind,
        size_bytes=size_bytes,
        modified_ns=modified_ns,
        hidden=item.name.startswith("."),
    )


def _entry_sort_key(entry: WorkspaceEntry) -> tuple[int, str, str]:
    bucket = 0 if entry.kind == WorkspaceEntryKind.DIRECTORY else 1
    return bucket, entry.name.casefold(), entry.name
