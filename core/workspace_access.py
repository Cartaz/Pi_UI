"""Shared confined filesystem primitives for AIOS workspace access."""

from __future__ import annotations

import os
import stat
from pathlib import Path


class WorkspaceAccessError(RuntimeError):
    """Raised when a workspace path cannot be accessed safely."""


def resolve_workspace_root(root: Path) -> Path:
    """Resolve the canonical workspace root and require a real directory."""

    try:
        resolved = root.expanduser().resolve(strict=True)
    except OSError as exc:
        raise WorkspaceAccessError(f"workspace unavailable: {exc}") from exc
    if not resolved.is_dir():
        raise WorkspaceAccessError("workspace root is not a directory")
    return resolved


def relative_parts(relative_path: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    """Validate a workspace-relative path without resolving filesystem links."""

    relative = Path(relative_path)
    if relative.is_absolute():
        raise WorkspaceAccessError("absolute workspace paths are not allowed")
    parts = tuple(part for part in relative.parts if part not in {"", "."})
    if any(part == ".." for part in parts):
        raise WorkspaceAccessError("parent traversal is not allowed")
    if not allow_empty and not parts:
        raise WorkspaceAccessError("workspace file path is empty")
    return parts


def open_directory_parts_fd(root: Path, parts: tuple[str, ...]) -> int:
    """Open a directory by descriptor, refusing symlink traversal at every step.

    ``root`` must already be the resolved canonical workspace root. The returned
    descriptor is owned by the caller.
    """

    required_flags = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required_flags):
        raise WorkspaceAccessError("secure workspace access is unavailable on this platform")

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC

    try:
        current_fd = os.open(root, flags)
    except OSError as exc:
        raise WorkspaceAccessError(f"workspace unavailable: {exc}") from exc

    try:
        for part in parts:
            try:
                metadata = os.stat(part, dir_fd=current_fd, follow_symlinks=False)
                if stat.S_ISLNK(metadata.st_mode):
                    raise WorkspaceAccessError("symlink directories are not traversable")
                next_fd = os.open(part, flags, dir_fd=current_fd)
            except WorkspaceAccessError:
                raise
            except OSError as exc:
                raise WorkspaceAccessError(f"directory path is not traversable: {exc}") from exc
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise
