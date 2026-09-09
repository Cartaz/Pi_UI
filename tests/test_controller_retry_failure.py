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


def test_explicit_reconnect_after_terminal_failure_restores_send_ready(
    tmp_path: Path,
) -> None:
    _write_profile(tmp_path)
    harness = Harness()
    controller = AgentController(
        SettingsStore(tmp_path / "settings.json"),
        harness.factory,
        settings=AppSettings(workspace_root=str(tmp_path)),
    )

    controller.connect_agent()
    first = _transport(harness)
    _hydrate_session(first, session_id="01recoverable", messages=[])

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
    _hydrate_session(
        second,
        session_id="01recoverable",
        messages=[
            {"role": "user", "content": "failed accepted prompt"},
            {
                "role": "assistant",
                "content": [],
                "stopReason": "error",
                "errorMessage": "server unavailable",
            },
        ],
    )

    assert controller.connection_state == ConnectionState.READY
    assert controller.turn_state == TurnState.IDLE
    assert controller.can_send is True
    assert len(controller.messages) == 1
    assert controller.messages[0].text == "failed accepted prompt"
    assert controller.messages[0].state == MessageState.FAILED
    assert [item["type"] for item in second.sent] == ["get_state", "get_messages"]


def _hydrate_session(
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
