"""Confined, read-only UTF-8 document previews for the AIOS workspace."""

from __future__ import annotations

import errno
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from core.workspace_access import (
    WorkspaceAccessError,
    open_directory_parts_fd,
    relative_parts,
    resolve_workspace_root,
)

MAX_PREVIEW_BYTES = 1_048_576
_READ_CHUNK_BYTES = 65_536


class WorkspaceDocumentStatus(StrEnum):
    READY = "ready"
    UNSUPPORTED = "unsupported"
    ERROR = "error"
    CANCELLED = "cancelled"


class WorkspaceDocumentReason(StrEnum):
    NONE = "none"
    SYMLINK = "symlink"
    NOT_REGULAR = "not-regular"
    TOO_LARGE = "too-large"
    BINARY = "binary"
    INVALID_UTF8 = "invalid-utf8"
    INVALID_PATH = "invalid-path"
    UNAVAILABLE = "unavailable"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class WorkspaceDocumentResult:
    relative_path: str
    status: WorkspaceDocumentStatus
    reason: WorkspaceDocumentReason = WorkspaceDocumentReason.NONE
    text: str = ""
    size_bytes: int = 0
    message: str = ""


CancelCheck = Callable[[], bool]


def load_document_preview(
    root: Path,
    relative_path: str,
    *,
    max_bytes: int = MAX_PREVIEW_BYTES,
    cancelled: CancelCheck | None = None,
) -> WorkspaceDocumentResult:
    """Load one UTF-8 text file without following workspace-relative symlinks.

    Parent components are opened by descriptor using ``O_DIRECTORY`` and
    ``O_NOFOLLOW``. The final path is lstat'd, opened with ``O_NOFOLLOW`` and
    then verified again with ``fstat``. ``O_NONBLOCK`` prevents a raced FIFO or
    device from blocking a worker thread before the post-open type check.
    """

    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if cancelled is not None and cancelled():
        return _cancelled(relative_path)

    try:
        root_resolved = resolve_workspace_root(root)
        parts = relative_parts(relative_path, allow_empty=False)
    except WorkspaceAccessError as exc:
        return WorkspaceDocumentResult(
            relative_path=relative_path,
            status=WorkspaceDocumentStatus.ERROR,
            reason=WorkspaceDocumentReason.INVALID_PATH,
            message=str(exc),
        )

    parent_fd: int | None = None
    file_fd: int | None = None
    try:
        parent_fd = open_directory_parts_fd(root_resolved, parts[:-1])
        name = parts[-1]

        try:
            before_open = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as exc:
            return _unavailable(relative_path, exc)

        if stat.S_ISLNK(before_open.st_mode):
            return _unsupported(
                relative_path,
                WorkspaceDocumentReason.SYMLINK,
                "Symlink previews are not allowed",
            )
        if not stat.S_ISREG(before_open.st_mode):
            return _unsupported(
                relative_path,
                WorkspaceDocumentReason.NOT_REGULAR,
                "Only regular files can be previewed",
            )
        if before_open.st_size > max_bytes:
            return _too_large(relative_path, before_open.st_size, max_bytes)

        flags = os.O_RDONLY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NONBLOCK"):
            flags |= os.O_NONBLOCK

        try:
            file_fd = os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                return _unsupported(
                    relative_path,
                    WorkspaceDocumentReason.SYMLINK,
                    "Symlink previews are not allowed",
                )
            return _unavailable(relative_path, exc)

        opened = os.fstat(file_fd)
        if not stat.S_ISREG(opened.st_mode):
            return _unsupported(
                relative_path,
                WorkspaceDocumentReason.NOT_REGULAR,
                "Only regular files can be previewed",
            )
        if opened.st_size > max_bytes:
            return _too_large(relative_path, opened.st_size, max_bytes)

        payload = _read_limited(file_fd, max_bytes, cancelled)
        if payload is None:
            return _cancelled(relative_path)
        if len(payload) > max_bytes:
            return _too_large(relative_path, len(payload), max_bytes)
        if _looks_binary(payload):
            return _unsupported(
                relative_path,
                WorkspaceDocumentReason.BINARY,
                "Binary-looking files are not previewed",
                size_bytes=len(payload),
            )

        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            return _unsupported(
                relative_path,
                WorkspaceDocumentReason.INVALID_UTF8,
                "File is not valid UTF-8 text",
                size_bytes=len(payload),
            )

        return WorkspaceDocumentResult(
            relative_path=relative_path,
            status=WorkspaceDocumentStatus.READY,
            text=text,
            size_bytes=len(payload),
        )
    except WorkspaceAccessError as exc:
        return WorkspaceDocumentResult(
            relative_path=relative_path,
            status=WorkspaceDocumentStatus.ERROR,
            reason=WorkspaceDocumentReason.UNAVAILABLE,
            message=str(exc),
        )
    except OSError as exc:
        return _unavailable(relative_path, exc)
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if parent_fd is not None:
            os.close(parent_fd)


def _read_limited(
    file_fd: int,
    max_bytes: int,
    cancelled: CancelCheck | None,
) -> bytes | None:
    chunks: list[bytes] = []
    total = 0
    while total <= max_bytes:
        if cancelled is not None and cancelled():
            return None
        chunk = os.read(file_fd, min(_READ_CHUNK_BYTES, max_bytes + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


def _looks_binary(payload: bytes) -> bool:
    if not payload:
        return False
    if b"\x00" in payload:
        return True

    sample = payload[:8192]
    allowed_controls = {8, 9, 10, 12, 13}
    suspicious = sum(byte < 32 and byte not in allowed_controls for byte in sample)
    return suspicious / len(sample) > 0.10


def _too_large(relative_path: str, size_bytes: int, max_bytes: int) -> WorkspaceDocumentResult:
    return _unsupported(
        relative_path,
        WorkspaceDocumentReason.TOO_LARGE,
        f"File exceeds the {max_bytes} byte preview limit",
        size_bytes=size_bytes,
    )


def _unsupported(
    relative_path: str,
    reason: WorkspaceDocumentReason,
    message: str,
    *,
    size_bytes: int = 0,
) -> WorkspaceDocumentResult:
    return WorkspaceDocumentResult(
        relative_path=relative_path,
        status=WorkspaceDocumentStatus.UNSUPPORTED,
        reason=reason,
        size_bytes=size_bytes,
        message=message,
    )


def _unavailable(relative_path: str, exc: OSError) -> WorkspaceDocumentResult:
    detail = exc.strerror or exc.__class__.__name__
    return WorkspaceDocumentResult(
        relative_path=relative_path,
        status=WorkspaceDocumentStatus.ERROR,
        reason=WorkspaceDocumentReason.UNAVAILABLE,
        message=f"File is unavailable: {detail}",
    )


def _cancelled(relative_path: str) -> WorkspaceDocumentResult:
    return WorkspaceDocumentResult(
        relative_path=relative_path,
        status=WorkspaceDocumentStatus.CANCELLED,
        reason=WorkspaceDocumentReason.CANCELLED,
    )
