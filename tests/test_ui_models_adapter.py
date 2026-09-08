from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from PySide6.QtCore import QModelIndex

from controllers.agent_controller import AgentController
from core.agent.runtime import PiLaunchSpec
from core.agent.transport import TransportState
from core.settings import AppSettings, SettingsStore
from ui.adapters import AgentAdapter
from ui.models import AgentProfileListModel, MessageListModel


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

    def set_record_handler(self, handler):
        self.record_handler = handler

    def set_diagnostic_handler(self, handler):
        self.diagnostic_handler = handler

    def set_error_handler(self, handler):
        self.error_handler = handler

    def set_state_handler(self, handler):
        self.state_handler = handler

    def start(self) -> None:
        self._state = TransportState.READY
        self.state_handler(self._state)

    def send(self, command: Mapping[str, Any]) -> None:
        self.sent.append(dict(command))

    def stop(self) -> None:
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


def test_qt_models_and_adapter_follow_controller_without_duplicate_state(
    tmp_path: Path,
) -> None:
    _write_profile(tmp_path)
    harness = Harness()
    controller = AgentController(
        SettingsStore(tmp_path / "settings.json"),
        harness.factory,
        settings=AppSettings(workspace_root=str(tmp_path)),
    )
    messages = MessageListModel(controller)
    profiles = AgentProfileListModel(controller)
    adapter = AgentAdapter(controller)

    assert profiles.rowCount() == 1
    assert profiles.data(profiles.index(0, 0), profiles.LabelRole) == "Ornith · ornith-lan"
    assert adapter.selectedProfileIndex == 0
    assert adapter.canConnect is True

    assert adapter.connectAgent() is True
    transport = _transport(harness)
    history = transport.sent[-1]
    transport.emit(
        {
            "id": history["id"],
            "type": "response",
            "command": "get_messages",
            "success": True,
            "data": {"messages": []},
        }
    )
    assert adapter.canSend is True

    assert adapter.sendMessage("hello") is True
    assert messages.rowCount() == 1
    first = messages.index(0, 0)
    assert messages.data(first, messages.TextRole) == "hello"
    assert messages.data(first, messages.StateRole) == "sending"

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
    assert messages.data(first, messages.StateRole) == "accepted"

    transport.emit(
        {
            "type": "message_update",
            "assistantMessageEvent": {
                "type": "text_delta",
                "contentIndex": 0,
                "delta": "reply",
            },
        }
    )
    assert messages.rowCount() == 2
    second = messages.index(1, 0)
    assert messages.data(second, messages.MessageRoleRole) == "assistant"
    assert messages.data(second, messages.TextRole) == "reply"
    assert messages.data(second, messages.StateRole) == "streaming"

    assert messages.rowCount(QModelIndex()) == 2


def test_adapter_rejects_missing_workspace_without_mutating_controller(
    tmp_path: Path,
) -> None:
    harness = Harness()
    controller = AgentController(
        SettingsStore(tmp_path / "settings.json"),
        harness.factory,
        settings=AppSettings(),
    )
    adapter = AgentAdapter(controller)

    assert adapter.setWorkspacePath(str(tmp_path / "missing")) is False
    assert adapter.hasWorkspace is False
    assert "workspace does not exist" in adapter.lastError


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
                        "baseUrl": "http://192.0.2.99:8080/v1",
                        "api": "openai-completions",
                        "apiKey": "pi-ui-local",
                        "models": [{"id": "Ornith"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
