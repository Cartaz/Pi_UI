from __future__ import annotations

import os
from pathlib import Path

from core.workspace_document import (
    MAX_PREVIEW_BYTES,
    WorkspaceDocumentReason,
    WorkspaceDocumentStatus,
    load_document_preview,
)


def test_loads_utf8_exactly_and_strips_only_leading_bom(tmp_path: Path) -> None:
    path = tmp_path / "Äppunti.md"
    path.write_bytes(b"\xef\xbb\xbfprima\r\nseconda\n\xf0\x9f\x8c\x8d")

    result = load_document_preview(tmp_path, "Äppunti.md")

    assert result.status == WorkspaceDocumentStatus.READY
    assert result.reason == WorkspaceDocumentReason.NONE
    assert result.text == "prima\r\nseconda\n🌍"
    assert result.size_bytes == path.stat().st_size


def test_empty_text_file_previews_successfully(tmp_path: Path) -> None:
    (tmp_path / "empty.txt").write_bytes(b"")

    result = load_document_preview(tmp_path, "empty.txt")

    assert result.status == WorkspaceDocumentStatus.READY
    assert result.text == ""
    assert result.size_bytes == 0


def test_rejects_symlink_even_when_target_is_inside_workspace(tmp_path: Path) -> None:
    (tmp_path / "real.txt").write_text("inside", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(tmp_path / "real.txt")

    result = load_document_preview(tmp_path, "link.txt")

    assert result.status == WorkspaceDocumentStatus.UNSUPPORTED
    assert result.reason == WorkspaceDocumentReason.SYMLINK
    assert result.text == ""


def test_rejects_directory_binary_invalid_utf8_and_oversized_file(tmp_path: Path) -> None:
    (tmp_path / "folder").mkdir()
    (tmp_path / "binary.bin").write_bytes(b"hello\x00world")
    (tmp_path / "invalid.txt").write_bytes(b"valid\xffinvalid")
    (tmp_path / "huge.txt").write_bytes(b"x" * (MAX_PREVIEW_BYTES + 1))

    directory = load_document_preview(tmp_path, "folder")
    binary = load_document_preview(tmp_path, "binary.bin")
    invalid = load_document_preview(tmp_path, "invalid.txt")
    huge = load_document_preview(tmp_path, "huge.txt")

    assert (directory.status, directory.reason) == (
        WorkspaceDocumentStatus.UNSUPPORTED,
        WorkspaceDocumentReason.NOT_REGULAR,
    )
    assert (binary.status, binary.reason) == (
        WorkspaceDocumentStatus.UNSUPPORTED,
        WorkspaceDocumentReason.BINARY,
    )
    assert (invalid.status, invalid.reason) == (
        WorkspaceDocumentStatus.UNSUPPORTED,
        WorkspaceDocumentReason.INVALID_UTF8,
    )
    assert (huge.status, huge.reason) == (
        WorkspaceDocumentStatus.UNSUPPORTED,
        WorkspaceDocumentReason.TOO_LARGE,
    )
    assert all(result.text == "" for result in (directory, binary, invalid, huge))


def test_rejects_absolute_parent_and_symlink_parent_paths(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    (tmp_path / "escape").symlink_to(outside, target_is_directory=True)

    absolute = load_document_preview(tmp_path, str(tmp_path / "anything.txt"))
    parent = load_document_preview(tmp_path, "../secret.txt")
    escaped = load_document_preview(tmp_path, "escape/secret.txt")

    assert absolute.status == WorkspaceDocumentStatus.ERROR
    assert absolute.reason == WorkspaceDocumentReason.INVALID_PATH
    assert parent.status == WorkspaceDocumentStatus.ERROR
    assert parent.reason == WorkspaceDocumentReason.INVALID_PATH
    assert escaped.status == WorkspaceDocumentStatus.ERROR
    assert escaped.reason == WorkspaceDocumentReason.UNAVAILABLE
    assert "secret" not in escaped.text


def test_final_file_replaced_by_outside_symlink_fails_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "target.txt"
    target.write_text("safe", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-race-secret.txt"
    outside.write_text("outside-secret", encoding="utf-8")

    real_open = os.open
    swapped = False

    def racing_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if path == "target.txt" and dir_fd is not None and not swapped:
            swapped = True
            target.unlink()
            target.symlink_to(outside)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr("core.workspace_document.os.open", racing_open)

    result = load_document_preview(tmp_path, "target.txt")

    assert swapped
    assert result.status == WorkspaceDocumentStatus.UNSUPPORTED
    assert result.reason == WorkspaceDocumentReason.SYMLINK
    assert "outside-secret" not in result.text


def test_cancellation_returns_no_document_content(tmp_path: Path) -> None:
    (tmp_path / "note.txt").write_text("content", encoding="utf-8")

    result = load_document_preview(tmp_path, "note.txt", cancelled=lambda: True)

    assert result.status == WorkspaceDocumentStatus.CANCELLED
    assert result.reason == WorkspaceDocumentReason.CANCELLED
    assert result.text == ""
