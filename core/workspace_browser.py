"""Confined, read-only directory scanning for the AIOS workspace browser."""

from __future__ import annotations

import os
import stat
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
    """Scan exactly one directory without recursively traversing the workspace.

    Every directory component is opened by file descriptor with ``O_NOFOLLOW``
    and ``O_DIRECTORY``. This makes symlink confinement an OS-enforced property
    at open time rather than a path check that can be raced by another process.
    Symlink entries remain visible leaf nodes in this first M1 browser slice.
    """

    try:
        root_resolved = root.expanduser().resolve(strict=True)
    except OSError as exc:
        return WorkspaceScanResult(relative_directory, (), f"workspace unavailable: {exc}")
    if not root_resolved.is_dir():
        return WorkspaceScanResult(relative_directory, (), "workspace root is not a directory")

    try:
        parts = _relative_parts(relative_directory)
        directory_fd = _open_directory_fd(root_resolved, parts)
    except WorkspaceBrowseError as exc:
        return WorkspaceScanResult(relative_directory, (), str(exc))

    prefix = "/".join(parts)
    entries: list[WorkspaceEntry] = []
    try:
        with os.scandir(directory_fd) as iterator:
            for item in iterator:
                if cancelled is not None and cancelled():
                    return WorkspaceScanResult(relative_directory, ())
                entries.append(_entry_from_dirent(prefix, item))
    except OSError as exc:
        return WorkspaceScanResult(relative_directory, (), f"cannot read directory: {exc}")
    finally:
        os.close(directory_fd)

    entries.sort(key=_entry_sort_key)
    return WorkspaceScanResult(relative_directory, tuple(entries))


def _relative_parts(relative_directory: str) -> tuple[str, ...]:
    relative = Path(relative_directory)
    if relative.is_absolute():
        raise WorkspaceBrowseError("absolute browser paths are not allowed")
    parts = tuple(part for part in relative.parts if part not in {"", "."})
    if any(part == ".." for part in parts):
        raise WorkspaceBrowseError("parent traversal is not allowed")
    return parts


def _open_directory_fd(root: Path, parts: tuple[str, ...]) -> int:
    required_flags = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required_flags):
        raise WorkspaceBrowseError("secure directory browsing is unavailable on this platform")

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC

    try:
        current_fd = os.open(root, flags)
    except OSError as exc:
        raise WorkspaceBrowseError(f"workspace unavailable: {exc}") from exc

    try:
        for part in parts:
            try:
                metadata = os.stat(part, dir_fd=current_fd, follow_symlinks=False)
                if stat.S_ISLNK(metadata.st_mode):
                    raise WorkspaceBrowseError("symlink directories are not traversable")
                next_fd = os.open(part, flags, dir_fd=current_fd)
            except WorkspaceBrowseError:
                raise
            except OSError as exc:
                raise WorkspaceBrowseError(f"directory path is not traversable: {exc}") from exc
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def _entry_from_dirent(prefix: str, item: os.DirEntry[str]) -> WorkspaceEntry:
    relative_path = f"{prefix}/{item.name}" if prefix else item.name
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
