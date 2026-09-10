from __future__ import annotations

import pytest

from core.agent.session_recovery import SessionRecoveryError, trailing_failed_user_entry_id


def _user(entry_id: str, parent_id: str | None, text: str) -> dict[str, object]:
    return {
        "type": "message",
        "id": entry_id,
        "parentId": parent_id,
        "message": {"role": "user", "content": text},
    }


def _assistant(
    entry_id: str,
    parent_id: str,
    *,
    stop_reason: str,
) -> dict[str, object]:
    return {
        "type": "message",
        "id": entry_id,
        "parentId": parent_id,
        "message": {
            "role": "assistant",
            "content": [],
            "stopReason": stop_reason,
        },
    }


def test_returns_last_user_entry_when_active_turn_ends_in_error() -> None:
    entries = [
        _user("u1", None, "first"),
        _assistant("a1", "u1", stop_reason="stop"),
        _user("u2", "a1", "failed"),
        _assistant("a2", "u2", stop_reason="error"),
    ]

    assert trailing_failed_user_entry_id(entries, "a2") == "u2"


def test_retry_error_followed_by_success_is_not_recovered() -> None:
    entries = [
        _user("u1", None, "retry me"),
        _assistant("a1", "u1", stop_reason="error"),
        _assistant("a2", "a1", stop_reason="stop"),
    ]

    assert trailing_failed_user_entry_id(entries, "a2") is None


def test_abandoned_failed_branch_is_ignored() -> None:
    entries = [
        _user("u1", None, "root"),
        _assistant("a1", "u1", stop_reason="stop"),
        _user("failed-user", "a1", "failed branch"),
        _assistant("failed-assistant", "failed-user", stop_reason="error"),
        _user("good-user", "a1", "good branch"),
        _assistant("good-assistant", "good-user", stop_reason="stop"),
    ]

    assert trailing_failed_user_entry_id(entries, "good-assistant") is None
    assert (
        trailing_failed_user_entry_id(entries, "failed-assistant")
        == "failed-user"
    )


def test_non_message_leaf_after_error_preserves_terminal_failure() -> None:
    entries = [
        _user("u1", None, "failed"),
        _assistant("a1", "u1", stop_reason="error"),
        {
            "type": "label",
            "id": "label1",
            "parentId": "a1",
            "targetId": "u1",
        },
    ]

    assert trailing_failed_user_entry_id(entries, "label1") == "u1"


def test_empty_session_has_no_recovery_candidate() -> None:
    assert trailing_failed_user_entry_id([], None) is None


def test_missing_leaf_parent_fails_closed() -> None:
    entries = [_user("u1", "missing", "broken")]

    with pytest.raises(SessionRecoveryError, match="missing parent"):
        trailing_failed_user_entry_id(entries, "u1")


def test_cycle_fails_closed() -> None:
    entries = [
        _user("u1", "a1", "cycle"),
        _assistant("a1", "u1", stop_reason="error"),
    ]

    with pytest.raises(SessionRecoveryError, match="cyclic"):
        trailing_failed_user_entry_id(entries, "a1")
