from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from controllers.agent_controller import AgentController, ConnectionState, MessageState
from core.agent.runtime import PiLaunchSpec
from core.agent.transport import TransportState
from core.settings import AppSettings, SettingsStore


class ManualHandle:
    def __init__(self, callback: Callable[[], None]) -> None:
        self.callback = callback
        self.cancelled = False
        self.fired = False

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        if self.cancelled or self.fired:
            return
        self.fired = True
        self.callback()


class ManualScheduler:
    def __init__(self) -> None:
        self.scheduled: list[tuple[int, ManualHandle]] = []

    def call_later(self, delay_ms: int, callback: Callable[[], None]) -> ManualHandle:
        handle = ManualHandle(callback)
        self.scheduled.append((delay_ms, handle))
        return handle

    def latest(self, delay_ms: int) -> ManualHandle:
        for delay, handle in reversed(self.scheduled):
            if delay == delay_ms and not handle.cancelled and not handle.fired:
                return handle
        raise AssertionError(f"no active deadline for {delay_ms} ms")


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
        if self._state != TransportState.READY:
            raise RuntimeError("transport not ready")
        self.sent.append(dict(command))

    def stop(self) -> None:
        if self._state == TransportState.STOPPED:
            return
        self._state = TransportState.STOPPING
        self.state_handler(self._state)
        self._state = TransportState.STOPPED
        self.state_handler(self._state)

    def emit(self, record: dict[str, Any]) -> None:
        self.record_handler(record)


class Harness:
    def __init__(self) -> None:
        self.transport: FakeTransport | None = None
        self.scheduler = ManualScheduler()

    def transport_factory(
        self,
        _spec: PiLaunchSpec,
        _startup_timeout_ms: int,
        _shutdown_timeout_ms: int,
    ) -> FakeTransport:
        self.transport = FakeTransport()
        return self.transport

    def scheduler_factory(self) -> ManualScheduler:
        return self.scheduler


def _write_profile(tmp_path: Path) -> None:
    agent_dir = tmp_path / ".pi-agent"
    agent_dir.mkdir()
    (agent_dir / "models.json").write_text(
        json.dumps(
            {
                "providers": {
                    "ornith-lan": {
                        "baseUrl": "http://192.0.2.121:8080/v1",
                        "api": "openai-completions",
                        "apiKey": "pi-ui-local",
                        "models": [{"id": "Ornith"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def _controller(tmp_path: Path, harness: Harness) -> AgentController:
    _write_profile(tmp_path)
    return AgentController(
        SettingsStore(tmp_path / "app-settings.json"),
        harness.transport_factory,
        settings=AppSettings(workspace_root=str(tmp_path)),
        deadline_scheduler_factory=harness.scheduler_factory,
    )


def _transport(harness: Harness) -> FakeTransport:
    assert harness.transport is not None
    return harness.transport


def _connect_empty(controller: AgentController, harness: Harness) -> FakeTransport:
    controller.connect_agent()
    transport = _transport(harness)
    state = transport.sent[-1]
    assert state["type"] == "get_state"
    transport.emit(
        {
            "id": state["id"],
            "type": "response",
            "command": "get_state",
            "success": True,
            "data": {
                "sessionId": "01deadline",
                "sessionFile": "/workspace/.pi-agent/sessions/01deadline.jsonl",
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
            "data": {"messages": []},
        }
    )
    assert controller.connection_state == ConnectionState.READY
    return transport


def test_prompt_timeout_becomes_uncertain_without_retry(tmp_path: Path) -> None:
    harness = Harness()
    controller = _controller(tmp_path, harness)
    transport = _connect_empty(controller, harness)

    controller.send_message("Do one thing")
    assert transport.sent[-1]["type"] == "prompt"
    sent_count = len(transport.sent)

    harness.scheduler.latest(30_000).fire()

    assert len(transport.sent) == sent_count
    assert controller.messages[-1].state == MessageState.UNCERTAIN
    assert controller.connection_state == ConnectionState.READY
    assert controller.can_send is False
    assert controller.can_disconnect is True
    assert controller.last_error is not None
    assert "outcome is unknown" in controller.last_error
    assert "did not resend" in controller.last_error

    transport.emit({"type": "agent_settled"})
    assert controller.can_send is False
    assert "reconnect" in controller.status_text.lower()


def test_inactivity_warning_keeps_turn_running_and_stoppable(tmp_path: Path) -> None:
    harness = Harness()
    controller = _controller(tmp_path, harness)
    transport = _connect_empty(controller, harness)

    controller.send_message("Long local inference")
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

    sent_count = len(transport.sent)
    harness.scheduler.latest(180_000).fire()

    assert len(transport.sent) == sent_count
    assert controller.connection_state == ConnectionState.READY
    assert controller.can_stop is True
    assert controller.last_error is not None
    assert "was not killed or retried" in controller.status_text

    transport.emit(
        {
            "type": "message_update",
            "assistantMessageEvent": {
                "type": "text_delta",
                "contentIndex": 0,
                "delta": "alive",
            },
        }
    )

    assert controller.last_error is None
    assert controller.messages[-1].role == "assistant"
    assert controller.messages[-1].text == "alive"
    assert controller.can_stop is True


def test_session_state_timeout_fails_closed_and_stops_process(tmp_path: Path) -> None:
    harness = Harness()
    controller = _controller(tmp_path, harness)

    controller.connect_agent()
    transport = _transport(harness)
    assert transport.sent[-1]["type"] == "get_state"

    harness.scheduler.latest(30_000).fire()

    assert controller.connection_state == ConnectionState.FAILED
    assert controller.session_ready is False
