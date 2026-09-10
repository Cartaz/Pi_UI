from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from controllers.agent_controller import (
    AgentController,
    AgentControllerError,
    ConnectionState,
    MessageState,
    RuntimeProfileSource,
)
from core.agent.runtime import PiLaunchSpec
from core.agent.transport import TransportState
from core.settings import AgentSettings, AppSettings, SettingsStore


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

    def diagnostic(self, text: str) -> None:
        self.diagnostic_handler(text)


class TransportHarness:
    def __init__(self) -> None:
        self.transport: FakeTransport | None = None
        self.launch_spec: PiLaunchSpec | None = None
        self.launch_specs: list[PiLaunchSpec] = []
        self.timeouts: tuple[int, int] | None = None

    def factory(
        self,
        launch_spec: PiLaunchSpec,
        startup_timeout_ms: int,
        shutdown_timeout_ms: int,
    ) -> FakeTransport:
        self.launch_spec = launch_spec
        self.launch_specs.append(launch_spec)
        self.timeouts = (startup_timeout_ms, shutdown_timeout_ms)
        self.transport = FakeTransport()
        return self.transport


def test_existing_baseline_connects_fresh_and_streams_reply(tmp_path: Path) -> None:
    _write_existing_profile(tmp_path)
    harness = TransportHarness()
    controller = _controller(tmp_path, harness)

    assert controller.workspace == tmp_path.resolve()
    assert len(controller.profiles) == 1
    assert controller.selected_profile is not None
    assert controller.selected_profile.source == RuntimeProfileSource.EXISTING
    assert controller.can_connect is True

    controller.connect_agent()
    transport = _transport(harness)
    assert controller.connection_state == ConnectionState.LOADING_SESSION
    first_args = _pi_arguments(harness.launch_specs[-1])
    assert "--continue" not in first_args
    assert "--session" not in first_args
    assert transport.sent[-1]["type"] == "get_state"
    _emit_session_state(transport, session_id="01session")
    assert transport.sent[-1]["type"] == "get_messages"
    history_id = transport.sent[-1]["id"]
    transport.emit(
        {
            "id": history_id,
            "type": "response",
            "command": "get_messages",
            "success": True,
            "data": {"messages": []},
        }
    )

    assert controller.connection_state == ConnectionState.READY
    assert controller.can_send is True
    assert controller.settings.last_session_id == "01session"
    assert controller.messages == ()

    controller.send_message("New question")
    prompt = transport.sent[-1]
    assert prompt["type"] == "prompt"
    assert controller.messages[-1].state == MessageState.SENDING

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

    transport.emit(
        {
            "type": "message_update",
            "assistantMessageEvent": {
                "type": "text_delta",
                "contentIndex": 0,
                "delta": "Hello ",
            },
        }
    )
    transport.emit(
        {
            "type": "message_update",
            "assistantMessageEvent": {
                "type": "text_delta",
                "contentIndex": 0,
                "delta": "world",
            },
        }
    )
    assert controller.messages[-1].role == "assistant"
    assert controller.messages[-1].text == "Hello world"
    assert controller.messages[-1].state == MessageState.STREAMING

    transport.emit(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello world!"}],
            },
        }
    )
    transport.emit({"type": "agent_settled"})

    assert controller.messages[-1].text == "Hello world!"
    assert controller.messages[-1].state == MessageState.COMPLETE
    assert controller.can_send is True
    assert harness.launch_spec is not None
    assert harness.launch_spec.executable == "/usr/bin/bwrap"
    assert harness.timeouts == (10_000, 5_000)


def test_first_connect_ignores_unrelated_sessions_in_shared_directory(
    tmp_path: Path,
) -> None:
    _write_existing_profile(tmp_path)
    sessions = tmp_path / ".pi-agent" / "sessions"
    sessions.mkdir()
    (sessions / "foreign-session.jsonl").write_text("{}\n", encoding="utf-8")
    harness = TransportHarness()
    controller = _controller(tmp_path, harness)

    controller.connect_agent()

    args = _pi_arguments(harness.launch_specs[-1])
    assert "--continue" not in args
    assert "--session" not in args


def test_disconnect_reconnect_uses_exact_captured_session_and_restores_history(
    tmp_path: Path,
) -> None:
    _write_existing_profile(tmp_path)
    harness = TransportHarness()
    controller = _controller(tmp_path, harness)
    _connect_empty(controller, harness, session_id="01stable")

    first_args = _pi_arguments(harness.launch_specs[0])
    assert "--continue" not in first_args
    assert "--session" not in first_args

    controller.disconnect_agent()
    controller.connect_agent()
    transport = _transport(harness)
    second_args = _pi_arguments(harness.launch_specs[1])
    assert "--continue" not in second_args
    assert "--session" not in second_args
    session_index = second_args.index("--session-id")
    assert second_args[session_index + 1] == "01stable"

    _emit_session_state(transport, session_id="01stable")
    history = transport.sent[-1]
    assert history["type"] == "get_messages"
    transport.emit(
        {
            "id": history["id"],
            "type": "response",
            "command": "get_messages",
            "success": True,
            "data": {
                "messages": [
                    {"role": "user", "content": "Persist me"},
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Persisted"}],
                    },
                ]
            },
        }
    )

    assert controller.connection_state == ConnectionState.READY
    assert [(item.role, item.text) for item in controller.messages] == [
        ("user", "Persist me"),
        ("assistant", "Persisted"),
    ]


def test_app_restart_uses_persisted_exact_session_id(tmp_path: Path) -> None:
    _write_existing_profile(tmp_path)
    store = SettingsStore(tmp_path / "app-settings.json")
    first_harness = TransportHarness()
    first = AgentController(
        store,
        first_harness.factory,
        settings=AppSettings(workspace_root=str(tmp_path)),
    )
    _connect_empty(first, first_harness, session_id="01restart")
    first.disconnect_agent()

    second_harness = TransportHarness()
    restarted = AgentController(store, second_harness.factory)
    restarted.connect_agent()

    args = _pi_arguments(second_harness.launch_specs[-1])
    assert "--continue" not in args
    assert "--session" not in args
    session_index = args.index("--session-id")
    assert args[session_index + 1] == "01restart"


def test_session_identity_mismatch_fails_closed_and_stops_pi(tmp_path: Path) -> None:
    _write_existing_profile(tmp_path)
    harness = TransportHarness()
    store = SettingsStore(tmp_path / "app-settings.json")
    controller = AgentController(
        store,
        harness.factory,
        settings=AppSettings(
            workspace_root=str(tmp_path),
            last_session_id="01expected",
        ),
    )

    controller.connect_agent()
    transport = _transport(harness)
    _emit_session_state(transport, session_id="01different")

    assert transport.state == TransportState.STOPPED
    assert controller.connection_state == ConnectionState.FAILED
    assert controller.can_connect is True
    assert controller.last_error is not None
    assert "different session" in controller.last_error
    assert controller.messages == ()


def test_changing_workspace_clears_captured_session_pointer(tmp_path: Path) -> None:
    _write_existing_profile(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    harness = TransportHarness()
    store = SettingsStore(tmp_path / "app-settings.json")
    controller = AgentController(
        store,
        harness.factory,
        settings=AppSettings(
            workspace_root=str(tmp_path),
            last_session_id="01old",
        ),
    )

    controller.set_workspace(other)

    assert controller.settings.last_session_id is None
    assert store.load().last_session_id is None


def test_prompt_rejection_marks_only_local_user_message_failed(tmp_path: Path) -> None:
    _write_existing_profile(tmp_path)
    harness = TransportHarness()
    controller = _controller(tmp_path, harness)
    _connect_empty(controller, harness)

    controller.send_message("Rejected")
    transport = _transport(harness)
    request = transport.sent[-1]
    transport.emit(
        {
            "id": request["id"],
            "type": "response",
            "command": "prompt",
            "success": False,
            "error": {"message": "bad request"},
        }
    )

    assert controller.messages[-1].state == MessageState.FAILED
    assert controller.last_error == "bad request"
    assert controller.connection_state == ConnectionState.READY
    assert controller.can_send is True


def test_stop_uses_clear_queue_then_abort_and_surfaces_recovered_text(
    tmp_path: Path,
) -> None:
    _write_existing_profile(tmp_path)
    harness = TransportHarness()
    controller = _controller(tmp_path, harness)
    recovered: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    controller.set_recovered_queue_handler(
        lambda steering, follow: recovered.append((steering, follow))
    )
    _connect_empty(controller, harness)
    transport = _transport(harness)

    controller.send_message("Start")
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
    assert controller.can_stop is True

    controller.request_stop()
    clear = transport.sent[-1]
    assert clear["type"] == "clear_queue"
    transport.emit(
        {
            "id": clear["id"],
            "type": "response",
            "command": "clear_queue",
            "success": True,
            "data": {"steering": ["one"], "followUp": ["two"]},
        }
    )
    abort = transport.sent[-1]
    assert abort["type"] == "abort"
    assert recovered == [(('one',), ('two',))]

    transport.emit(
        {
            "id": abort["id"],
            "type": "response",
            "command": "abort",
            "success": True,
        }
    )
    transport.emit({"type": "agent_settled"})
    assert controller.can_send is True


def test_switching_workspace_is_blocked_while_pi_is_connected(tmp_path: Path) -> None:
    _write_existing_profile(tmp_path)
    harness = TransportHarness()
    controller = _controller(tmp_path, harness)
    _connect_empty(controller, harness)
    other = tmp_path / "other"
    other.mkdir()

    with pytest.raises(AgentControllerError, match="disconnect"):
        controller.set_workspace(other)


def test_disconnect_is_deterministic_and_allows_reconnect(tmp_path: Path) -> None:
    _write_existing_profile(tmp_path)
    harness = TransportHarness()
    controller = _controller(tmp_path, harness)
    _connect_empty(controller, harness)

    controller.disconnect_agent()

    assert controller.connection_state == ConnectionState.DISCONNECTED
    assert controller.session_ready is False
    assert controller.can_connect is True


def test_diagnostic_output_is_bounded(tmp_path: Path) -> None:
    _write_existing_profile(tmp_path)
    harness = TransportHarness()
    controller = _controller(tmp_path, harness)
    controller.connect_agent()
    transport = _transport(harness)

    transport.diagnostic("x" * 5000)

    assert len(controller.diagnostic_tail) == 4000


def test_configured_settings_profile_can_bootstrap_new_workspace(tmp_path: Path) -> None:
    harness = TransportHarness()
    store = SettingsStore(tmp_path / "app-settings.json")
    settings = AppSettings(
        workspace_root=str(tmp_path),
        agent=AgentSettings(
            provider="ornith-lan",
            model="Ornith",
            base_url="http://192.0.2.91:8080/v1",
        ),
    )
    controller = AgentController(store, harness.factory, settings=settings)

    assert controller.selected_profile is not None
    assert controller.selected_profile.source == RuntimeProfileSource.SETTINGS
    controller.connect_agent()

    assert (tmp_path / ".pi-agent/models.json").is_file()
    assert _transport(harness).sent[-1]["type"] == "get_state"


def _controller(tmp_path: Path, harness: TransportHarness) -> AgentController:
    store = SettingsStore(tmp_path / "app-settings.json")
    settings = AppSettings(workspace_root=str(tmp_path))
    return AgentController(store, harness.factory, settings=settings)


def _connect_empty(
    controller: AgentController,
    harness: TransportHarness,
    *,
    session_id: str = "01session",
) -> None:
    controller.connect_agent()
    transport = _transport(harness)
    state = transport.sent[-1]
    assert state["type"] == "get_state"
    _emit_session_state(transport, session_id=session_id)
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


def _emit_session_state(transport: FakeTransport, *, session_id: str) -> None:
    request = transport.sent[-1]
    assert request["type"] == "get_state"
    transport.emit(
        {
            "id": request["id"],
            "type": "response",
            "command": "get_state",
            "success": True,
            "data": {
                "sessionId": session_id,
                "sessionFile": f"/workspace/.pi-agent/sessions/{session_id}.jsonl",
            },
        }
    )


def _pi_arguments(spec: PiLaunchSpec) -> tuple[str, ...]:
    separator = spec.arguments.index("--")
    return spec.arguments[separator + 1 :]


def _transport(harness: TransportHarness) -> FakeTransport:
    assert harness.transport is not None
    return harness.transport


def _write_existing_profile(tmp_path: Path) -> None:
    agent_dir = tmp_path / ".pi-agent"
    agent_dir.mkdir(exist_ok=True)
    (agent_dir / "models.json").write_text(
        json.dumps(
            {
                "providers": {
                    "ornith-lan": {
                        "baseUrl": "http://192.0.2.90:8080/v1",
                        "api": "openai-completions",
                        "apiKey": "pi-ui-local",
                        "models": [{"id": "Ornith"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
