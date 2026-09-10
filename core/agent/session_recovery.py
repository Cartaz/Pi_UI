"""Pure analysis for recovering Pi sessions after terminal model failures."""

from __future__ import annotations

from typing import Any


class SessionRecoveryError(ValueError):
    """Raised when Pi session entries cannot be interpreted safely."""


def trailing_failed_user_entry_id(entries: object, leaf_id: object) -> str | None:
    """Return the active-branch user entry whose turn ended in an error.

    Pi sessions are append-only trees. ``get_entries`` returns every entry in
    append order, including abandoned branches, plus the current ``leafId``.
    Recovery must therefore inspect only the path from the active leaf to the
    root. The latest terminal assistant outcome for the last user turn decides
    whether that turn is failed; an intermediate error followed by a successful
    assistant completion is not a recovery candidate.
    """

    if leaf_id is None:
        return None
    if not isinstance(leaf_id, str) or not leaf_id:
        raise SessionRecoveryError("Pi returned an invalid session leaf id")
    if not isinstance(entries, list):
        raise SessionRecoveryError("Pi returned invalid session entries")

    by_id: dict[str, dict[str, Any]] = {}
    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            raise SessionRecoveryError("Pi returned a malformed session entry")
        entry_id = raw_entry.get("id")
        if not isinstance(entry_id, str) or not entry_id:
            raise SessionRecoveryError("Pi returned a session entry without a valid id")
        if entry_id in by_id:
            raise SessionRecoveryError("Pi returned duplicate session entry ids")
        by_id[entry_id] = raw_entry

    path_reversed: list[dict[str, Any]] = []
    seen: set[str] = set()
    current_id: str | None = leaf_id
    while current_id is not None:
        if current_id in seen:
            raise SessionRecoveryError("Pi returned a cyclic session branch")
        seen.add(current_id)
        entry = by_id.get(current_id)
        if entry is None:
            raise SessionRecoveryError("Pi session leaf references a missing parent entry")
        path_reversed.append(entry)
        parent_id = entry.get("parentId")
        if parent_id is not None and (
            not isinstance(parent_id, str) or not parent_id
        ):
            raise SessionRecoveryError("Pi returned an invalid session parent id")
        current_id = parent_id

    latest_user_entry_id: str | None = None
    terminal_outcome: str | None = None

    for entry in reversed(path_reversed):
        if entry.get("type") != "message":
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            raise SessionRecoveryError("Pi returned a malformed message entry")
        role = message.get("role")
        if role == "user":
            latest_user_entry_id = entry["id"]
            terminal_outcome = None
            continue
        if role != "assistant" or latest_user_entry_id is None:
            continue

        stop_reason = message.get("stopReason")
        if stop_reason == "error":
            terminal_outcome = "failed"
        elif stop_reason == "toolUse":
            continue
        else:
            # A later non-error assistant message supersedes an earlier retry
            # error for the same user turn.
            terminal_outcome = "complete"

    if latest_user_entry_id is not None and terminal_outcome == "failed":
        return latest_user_entry_id
    return None
