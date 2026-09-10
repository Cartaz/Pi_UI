from __future__ import annotations

import os
from pathlib import Path

from core.workspace_browser import WorkspaceEntryKind, scan_directory


def test_scan_directory_sorts_directories_before_files_and_preserves_unicode(
    tmp_path: Path,
) -> None:
    (tmp_path / "zeta.txt").write_text("z", encoding="utf-8")
    (tmp_path / "Äppunti.md").write_text("note", encoding="utf-8")
    (tmp_path / "beta").mkdir()
    (tmp_path / "Alpha").mkdir()

    result = scan_directory(tmp_path)

    assert result.error is None
    assert [(item.name, item.kind) for item in result.entries] == [
        ("Alpha", WorkspaceEntryKind.DIRECTORY),
        ("beta", WorkspaceEntryKind.DIRECTORY),
        ("zeta.txt", WorkspaceEntryKind.FILE),
        ("Äppunti.md", WorkspaceEntryKind.FILE),
    ]
    unicode_entry = next(item for item in result.entries if item.name == "Äppunti.md")
    assert unicode_entry.relative_path == "Äppunti.md"
    assert unicode_entry.size_bytes == len("note".encode())


def test_symlink_is_visible_but_never_expandable_or_traversable(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside", encoding="utf-8")
    (tmp_path / "escape").symlink_to(outside, target_is_directory=True)

    root = scan_directory(tmp_path)
    symlink = next(item for item in root.entries if item.name == "escape")

    assert symlink.kind == WorkspaceEntryKind.SYMLINK
    assert not symlink.can_expand

    escaped = scan_directory(tmp_path, "escape")
    assert escaped.entries == ()
    assert escaped.error == "symlink directories are not traversable"


def test_directory_replaced_by_symlink_cannot_race_secure_open(
    tmp_path: Path,
    monkeypatch,
) -> None:
    safe = tmp_path / "safe"
    safe.mkdir()
    (safe / "inside.txt").write_text("inside", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-race-outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")

    real_open = os.open
    swapped = False

    def racing_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if path == "safe" and dir_fd is not None and not swapped:
            swapped = True
            safe.rename(tmp_path / "safe-original")
            safe.symlink_to(outside, target_is_directory=True)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr("core.workspace_browser.os.open", racing_open)

    result = scan_directory(tmp_path, "safe")

    assert swapped
    assert result.entries == ()
    assert result.error is not None
    assert "not traversable" in result.error
    assert "secret.txt" not in {entry.name for entry in result.entries}


def test_scan_rejects_absolute_and_parent_paths(tmp_path: Path) -> None:
    absolute = scan_directory(tmp_path, str(tmp_path))
    parent = scan_directory(tmp_path, "../outside")

    assert absolute.error == "absolute browser paths are not allowed"
    assert parent.error == "parent traversal is not allowed"


def test_scan_only_reads_one_requested_directory(tmp_path: Path) -> None:
    nested = tmp_path / "one" / "two"
    nested.mkdir(parents=True)
    (nested / "deep.txt").write_text("deep", encoding="utf-8")

    root = scan_directory(tmp_path)
    one = next(item for item in root.entries if item.name == "one")

    assert one.kind == WorkspaceEntryKind.DIRECTORY
    assert all(item.name != "deep.txt" for item in root.entries)

    child = scan_directory(tmp_path, "one")
    assert [item.name for item in child.entries] == ["two"]
