from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from controllers.agent_controller import AgentController, ConnectionState, MessageState
from core.agent import TurnState
from core.agent.runtime import PiLaunchSpec
from core.agent.transport import TransportState
from core.settings import AppSettings, SettingsStore


class FakeTransport:
    def __init__(self) -> None:
        self._state = TransportState.STOPPED
        self.sent: list[dict[str, Any]] = []
        self.record_handler: Callable[[dict[str, Any]], None] = lambda _record: None
        self.diagnostic_handler: Callable[[str], None] = lambda _text: None
        self.error_handler: Callable[[BaseException], None] = lambda _error: None
        self.state_handler: Callable[[TransportState], None] = lambda _state: None

    @property
    def state(self) -> TransportState:
        return self._state

    def set_record_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        self.record_handler = handler

    def set_diagnostic_handler(self, handler: Callable[[str], None]) -> None:
        self.diagnostic_handler = handler

    def set_error_handler(self, handler: Callable[[BaseException], None]) -> None:
        self.error_handler = handler

    def set_state_handler(self, handler: Callable[[TransportState], None]) -> None:
        self.state_handler = handler

    def start(self) -> None:
        self._state = TransportState.STARTING
        self.state_handler(self._state)
        self._state = TransportState.READY
        self.state_handler(self._state)

    def send(self, command: Mapping[str, Any]) -> None:
        self.sent.append(dict(command))

    def stop(self) -> None:
        self._state = TransportState.STOPPING
        self.state_handler(self._state)
        self._state = TransportState.STOPPED
        self.state_handler(self._state)

    def emit(self, record: dict[str, Any]) -> None:
        self.record_handler(record)


class Harness:
    def __init__(self) -> None:
        self.transport: FakeTransport | None = None

    def factory(
        self,
        _launch_spec: PiLaunchSpec,
        _startup_timeout_ms: int,
        _shutdown_timeout_ms: int,
    ) -> FakeTransport:
        self.transport = FakeTransport()
        return self.transport


def test_terminal_retry_failure_never_returns_controller_to_ready(tmp_path: Path) -> None:
    _write_profile(tmp_path)
    harness = Harness()
    controller = AgentController(
        SettingsStore(tmp_path / "settings.json"),
        harness.factory,
        settings=AppSettings(workspace_root=str(tmp_path)),
    )

    controller.connect_agent()
    transport = _transport(harness)
    _hydrate_session(transport, session_id="01retryfailure", messages=[])
    assert controller.connection_state == ConnectionState.READY

    controller.send_message("work while server is down")
    prompt = transport.sent[-1]
    transport.emit({"type": "agent_start"})
    transport.emit(
        {
            "id": prompt["id"],
            "type": "response",
            "command": "prompt",
            "success": True,
        }
    )
    assert controller.messages[-1].state == MessageState.ACCEPTED

    for attempt in (1, 2, 3):
        transport.emit(
            {
                "type": "agent_end",
                "messages": [
                    {
                        "role": "assistant",
                        "content": [],
                        "stopReason": "error",
                        "errorMessage": "connection refused",
                    }
                ],
                "willRetry": attempt < 3,
            }
        )
        if attempt < 3:
            transport.emit(
                {
                    "type": "auto_retry_start",
                    "attempt": attempt,
                    "maxAttempts": 3,
                    "delayMs": 10,
                    "errorMessage": "connection refused",
                }
            )
            transport.emit({"type": "agent_start"})

    transport.emit(
        {
            "type": "auto_retry_end",
            "success": False,
            "attempt": 3,
            "finalError": "ECONNREFUSED 192.0.2.1:8080",
        }
    )

    assert controller.connection_state == ConnectionState.FAILED
    assert controller.can_send is False
    assert controller.can_disconnect is True
    assert controller.messages[-1].state == MessageState.FAILED
    assert controller.last_error is not None
    assert "after 3 attempts" in controller.last_error
    assert "ECONNREFUSED" in controller.last_error

    transport.emit({"type": "agent_settled"})

    assert controller.connection_state == ConnectionState.FAILED
    assert controller.can_send is False
    assert controller.can_disconnect is True
    assert controller.messages[-1].state == MessageState.FAILED
    assert controller.last_error is not None
    assert "ECONNREFUSED" in controller.last_error
    assert sum(item.get("type") == "prompt" for item in transport.sent) == 1


def test_reconnect_forks_before_failed_prompt_before_becoming_send_ready(
    tmp_path: Path,
) -> None:
    _write_profile(tmp_path)
    store = SettingsStore(tmp_path / "settings.json")
    harness = Harness()
    controller = AgentController(
        store,
        harness.factory,
        settings=AppSettings(workspace_root=str(tmp_path)),
    )

    prior_messages = [
        {"role": "user", "content": "prior question"},
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "prior answer"}],
            "stopReason": "stop",
        },
    ]
    controller.connect_agent()
    first = _transport(harness)
    _hydrate_session(first, session_id="01recoverable", messages=prior_messages)

    controller.send_message("failed accepted prompt")
    prompt = first.sent[-1]
    first.emit({"type": "agent_start"})
    first.emit(
        {
            "id": prompt["id"],
            "type": "response",
            "command": "prompt",
            "success": True,
        }
    )
    first.emit(
        {
            "type": "auto_retry_end",
            "success": False,
            "attempt": 3,
            "finalError": "server unavailable",
        }
    )
    first.emit({"type": "agent_settled"})

    assert controller.connection_state == ConnectionState.FAILED
    assert controller.turn_state == TurnState.FAILED
    assert controller.can_send is False
    assert controller.messages[-1].state == MessageState.FAILED

    controller.disconnect_agent()
    assert controller.connection_state == ConnectionState.DISCONNECTED

    controller.connect_agent()
    second = _transport(harness)
    assert second is not first
    assert controller.turn_state == TurnState.IDLE

    failed_history = [
        *prior_messages,
        {"role": "user", "content": "failed accepted prompt"},
        {
            "role": "assistant",
            "content": [],
            "stopReason": "error",
            "errorMessage": "server unavailable",
        },
    ]
    _emit_state_and_history(
        second,
        session_id="01recoverable",
        messages=failed_history,
    )

    assert controller.connection_state == ConnectionState.LOADING_SESSION
    assert controller.can_send is False
    assert controller.messages[-1].text == "failed accepted prompt"
    assert controller.messages[-1].state == MessageState.FAILED
    entries_request = second.sent[-1]
    assert entries_request["type"] == "get_entries"

    second.emit(
        {
            "id": entries_request["id"],
            "type": "response",
            "command": "get_entries",
            "success": True,
            "data": {
                "entries": [
                    _user_entry("u1", None, "prior question"),
                    _assistant_entry("a1", "u1", "stop", "prior answer"),
                    _user_entry("u2", "a1", "failed accepted prompt"),
                    _assistant_entry("a2", "u2", "error", ""),
                ],
                "leafId": "a2",
            },
        }
    )

    fork_request = second.sent[-1]
    assert fork_request["type"] == "fork"
    assert fork_request["entryId"] == "u2"
    assert sum(item.get("type") == "prompt" for item in second.sent) == 0

    second.emit(
        {
            "id": fork_request["id"],
            "type": "response",
            "command": "fork",
            "success": True,
            "data": {"text": "failed accepted prompt", "cancelled": False},
        }
    )

    recovered_state = second.sent[-1]
    assert recovered_state["type"] == "get_state"
    second.emit(
        {
            "id": recovered_state["id"],
            "type": "response",
            "command": "get_state",
            "success": True,
            "data": {
                "sessionId": "01recoveredbranch",
                "sessionFile": "/workspace/.pi-agent/sessions/01recoveredbranch.jsonl",
            },
        }
    )

    recovered_history = second.sent[-1]
    assert recovered_history["type"] == "get_messages"
    second.emit(
        {
            "id": recovered_history["id"],
            "type": "response",
            "command": "get_messages",
            "success": True,
            "data": {"messages": prior_messages},
        }
    )

    assert controller.connection_state == ConnectionState.READY
    assert controller.turn_state == TurnState.IDLE
    assert controller.can_send is True
    assert controller.settings.last_session_id == "01recoveredbranch"
    assert store.load().last_session_id == "01recoveredbranch"
    assert [(item.role, item.text) for item in controller.messages] == [
        ("user", "prior question"),
        ("assistant", "prior answer"),
    ]
    assert all(item.text != "failed accepted prompt" for item in controller.messages)
    assert sum(item.get("type") == "prompt" for item in second.sent) == 0

    controller.send_message("new prompt only")
    new_prompt = second.sent[-1]
    assert new_prompt["type"] == "prompt"
    assert new_prompt["message"] == "new prompt only"
    assert sum(item.get("type") == "prompt" for item in second.sent) == 1


def test_recovery_fails_closed_when_active_tree_does_not_match_failed_history(
    tmp_path: Path,
) -> None:
    _write_profile(tmp_path)
    harness = Harness()
    controller = AgentController(
        SettingsStore(tmp_path / "settings.json"),
        harness.factory,
        settings=AppSettings(
            workspace_root=str(tmp_path),
            last_session_id="01mismatch",
        ),
    )

    controller.connect_agent()
    transport = _transport(harness)
    _emit_state_and_history(
        transport,
        session_id="01mismatch",
        messages=[
            {"role": "user", "content": "failed"},
            {
                "role": "assistant",
                "content": [],
                "stopReason": "error",
            },
        ],
    )
    entries_request = transport.sent[-1]
    assert entries_request["type"] == "get_entries"

    transport.emit(
        {
            "id": entries_request["id"],
            "type": "response",
            "command": "get_entries",
            "success": True,
            "data": {
                "entries": [
                    _user_entry("u1", None, "successful"),
                    _assistant_entry("a1", "u1", "stop", "done"),
                ],
                "leafId": "a1",
            },
        }
    )

    assert controller.connection_state == ConnectionState.FAILED
    assert controller.can_send is False
    assert controller.last_error is not None
    assert "active session branch did not" in controller.last_error
    assert sum(item.get("type") == "fork" for item in transport.sent) == 0


def _hydrate_session(
    transport: FakeTransport,
    *,
    session_id: str,
    messages: list[dict[str, Any]],
) -> None:
    _emit_state_and_history(transport, session_id=session_id, messages=messages)


def _emit_state_and_history(
    transport: FakeTransport,
    *,
    session_id: str,
    messages: list[dict[str, Any]],
) -> None:
    state = transport.sent[-1]
    assert state["type"] == "get_state"
    transport.emit(
        {
            "id": state["id"],
            "type": "response",
            "command": "get_state",
            "success": True,
            "data": {
                "sessionId": session_id,
                "sessionFile": f"/workspace/.pi-agent/sessions/{session_id}.jsonl",
            },
        }
    )
    history = transport.sent[-1]
    assert history["type"] == "get_messages"
    transport.emit(
        {
            "id": history["id"],
            "type": "response",
            "command": "get_messages",
            "success": True,
            "data": {"messages": messages},
        }
    )


def _user_entry(
    entry_id: str,
    parent_id: str | None,
    text: str,
) -> dict[str, Any]:
    return {
        "type": "message",
        "id": entry_id,
        "parentId": parent_id,
        "message": {"role": "user", "content": text},
    }


def _assistant_entry(
    entry_id: str,
    parent_id: str,
    stop_reason: str,
    text: str,
) -> dict[str, Any]:
    return {
        "type": "message",
        "id": entry_id,
        "parentId": parent_id,
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": text}] if text else [],
            "stopReason": stop_reason,
        },
    }


def _transport(harness: Harness) -> FakeTransport:
    assert harness.transport is not None
    return harness.transport


def _write_profile(tmp_path: Path) -> None:
    agent_dir = tmp_path / ".pi-agent"
    agent_dir.mkdir()
    (agent_dir / "models.json").write_text(
        json.dumps(
            {
                "providers": {
                    "ornith-lan": {
                        "baseUrl": "http://192.0.2.1:8080/v1",
                        "api": "openai-completions",
                        "apiKey": "pi-ui-local",
                        "models": [{"id": "Ornith"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
