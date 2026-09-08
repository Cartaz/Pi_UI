from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import pytest

from core.agent.client import AgentClient, AgentClientError, TurnState
from core.agent.transport import TransportState


class FakeTransport:
    def __init__(self) -> None:
        self._state = TransportState.STOPPED
        self.sent: list[dict[str, Any]] = []
        self._record_handler: Callable[[dict[str, Any]], None] = lambda _record: None
        self._diagnostic_handler: Callable[[str], None] = lambda _text: None
        self._error_handler: Callable[[BaseException], None] = lambda _error: None
        self._state_handler: Callable[[TransportState], None] = lambda _state: None

    @property
    def state(self) -> TransportState:
        return self._state

    def set_record_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        self._record_handler = handler

    def set_diagnostic_handler(self, handler: Callable[[str], None]) -> None:
        self._diagnostic_handler = handler

    def set_error_handler(self, handler: Callable[[BaseException], None]) -> None:
        self._error_handler = handler

    def set_state_handler(self, handler: Callable[[TransportState], None]) -> None:
        self._state_handler = handler

    def start(self) -> None:
        self._state = TransportState.READY
        self._state_handler(self._state)

    def send(self, command: Mapping[str, Any]) -> None:
        if self._state is not TransportState.READY:
            raise RuntimeError("not ready")
        self.sent.append(dict(command))

    def stop(self) -> None:
        self._state = TransportState.STOPPED
        self._state_handler(self._state)

    def emit_record(self, record: dict[str, Any]) -> None:
        self._record_handler(record)

    def emit_error(self, error: BaseException) -> None:
        self._error_handler(error)


def id_sequence() -> Callable[[], str]:
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"req-{counter}"

    return next_id


def test_prompt_response_acceptance_is_not_turn_completion() -> None:
    transport = FakeTransport()
    client = AgentClient(transport, id_factory=id_sequence())
    states: list[TurnState] = []
    responses: list[dict[str, Any]] = []
    client.set_turn_state_handler(states.append)
    client.set_response_handler(responses.append)
    client.start()

    request_id = client.prompt("hello")
    assert request_id == "req-1"
    assert transport.sent == [{"type": "prompt", "message": "hello", "id": "req-1"}]

    transport.emit_record({"type": "agent_start"})
    assert client.turn_state is TurnState.RUNNING

    transport.emit_record(
        {
            "id": "req-1",
            "type": "response",
            "command": "prompt",
            "success": True,
        }
    )
    assert client.turn_state is TurnState.RUNNING
    assert client.pending_request_ids == ()
    assert responses[-1]["success"] is True

    transport.emit_record({"type": "agent_end", "messages": []})
    assert client.turn_state is TurnState.RUNNING

    transport.emit_record({"type": "agent_settled"})
    assert client.turn_state is TurnState.IDLE
    assert states == [TurnState.RUNNING, TurnState.IDLE]


def test_stop_clears_queue_before_abort_and_restores_text() -> None:
    transport = FakeTransport()
    client = AgentClient(transport, id_factory=id_sequence())
    cleared: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    client.set_queue_cleared_handler(lambda steering, follow: cleared.append((steering, follow)))
    client.start()

    clear_id = client.request_stop()
    assert clear_id == "req-1"
    assert client.turn_state is TurnState.CANCELLING
    assert transport.sent[-1] == {"type": "clear_queue", "id": "req-1"}

    transport.emit_record(
        {
            "id": "req-1",
            "type": "response",
            "command": "clear_queue",
            "success": True,
            "data": {
                "steering": ["change direction"],
                "followUp": ["summarize later"],
            },
        }
    )

    assert cleared == [(('change direction',), ('summarize later',))]
    assert transport.sent[-1] == {"type": "abort", "id": "req-2"}

    transport.emit_record(
        {
            "id": "req-2",
            "type": "response",
            "command": "abort",
            "success": True,
        }
    )
    assert client.turn_state is TurnState.CANCELLING

    transport.emit_record({"type": "agent_settled"})
    assert client.turn_state is TurnState.IDLE


def test_prompt_streaming_behavior_is_validated() -> None:
    client = AgentClient(FakeTransport(), id_factory=id_sequence())
    with pytest.raises(AgentClientError, match="streaming_behavior"):
        client.prompt("hello", streaming_behavior="later")


def test_transport_failure_marks_active_turn_failed() -> None:
    transport = FakeTransport()
    client = AgentClient(transport, id_factory=id_sequence())
    errors: list[BaseException] = []
    client.set_error_handler(errors.append)
    client.start()
    transport.emit_record({"type": "agent_start"})

    error = RuntimeError("process crashed")
    transport.emit_error(error)

    assert client.turn_state is TurnState.FAILED
    assert errors == [error]
