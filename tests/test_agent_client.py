from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import pytest

from core.agent.client import (
    AgentClient,
    AgentClientError,
    AgentTurnFailedError,
    TurnState,
)
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
        if self._state != TransportState.READY:
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


def test_start_publishes_initial_idle_turn_state() -> None:
    transport = FakeTransport()
    client = AgentClient(transport, id_factory=id_sequence())
    states: list[TurnState] = []
    client.set_turn_state_handler(states.append)

    client.start()

    assert states == [TurnState.IDLE]
    assert client.turn_state == TurnState.IDLE


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
    assert client.turn_state == TurnState.RUNNING

    transport.emit_record(
        {
            "id": "req-1",
            "type": "response",
            "command": "prompt",
            "success": True,
        }
    )
    assert client.turn_state == TurnState.RUNNING
    assert client.pending_request_ids == ()
    assert responses[-1]["success"] is True

    transport.emit_record({"type": "agent_end", "messages": [], "willRetry": False})
    assert client.turn_state == TurnState.RUNNING

    transport.emit_record({"type": "agent_settled"})
    assert client.turn_state == TurnState.IDLE
    assert states == [TurnState.IDLE, TurnState.RUNNING, TurnState.IDLE]


def test_terminal_retry_failure_stays_failed_after_agent_settled() -> None:
    transport = FakeTransport()
    client = AgentClient(transport, id_factory=id_sequence())
    errors: list[BaseException] = []
    states: list[TurnState] = []
    client.set_error_handler(errors.append)
    client.set_turn_state_handler(states.append)
    client.start()

    client.prompt("hello")
    transport.emit_record({"type": "agent_start"})
    transport.emit_record(
        {
            "id": "req-1",
            "type": "response",
            "command": "prompt",
            "success": True,
        }
    )
    transport.emit_record(
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
            "willRetry": True,
        }
    )
    transport.emit_record(
        {
            "type": "auto_retry_start",
            "attempt": 1,
            "maxAttempts": 3,
            "delayMs": 100,
            "errorMessage": "connection refused",
        }
    )
    transport.emit_record(
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
            "willRetry": False,
        }
    )
    assert client.turn_state == TurnState.RUNNING

    transport.emit_record(
        {
            "type": "auto_retry_end",
            "success": False,
            "attempt": 3,
            "finalError": "ECONNREFUSED 192.0.2.1:8080",
        }
    )

    assert client.turn_state == TurnState.FAILED
    assert len(errors) == 1
    assert isinstance(errors[0], AgentTurnFailedError)
    assert errors[0].attempts == 3
    assert "after 3 attempts" in str(errors[0])
    assert "ECONNREFUSED" in str(errors[0])

    transport.emit_record({"type": "agent_settled"})

    assert client.turn_state == TurnState.FAILED
    assert states == [TurnState.IDLE, TurnState.RUNNING, TurnState.FAILED]


def test_non_retryable_agent_error_is_terminal() -> None:
    transport = FakeTransport()
    client = AgentClient(transport, id_factory=id_sequence())
    errors: list[BaseException] = []
    client.set_error_handler(errors.append)
    client.start()

    transport.emit_record({"type": "agent_start"})
    transport.emit_record(
        {
            "type": "agent_end",
            "messages": [
                {
                    "role": "assistant",
                    "content": [],
                    "stopReason": "error",
                    "errorMessage": "invalid request",
                }
            ],
            "willRetry": False,
        }
    )
    transport.emit_record({"type": "agent_settled"})

    assert client.turn_state == TurnState.FAILED
    assert len(errors) == 1
    assert isinstance(errors[0], AgentTurnFailedError)
    assert errors[0].attempts is None
    assert "invalid request" in str(errors[0])


def test_retry_cancellation_during_explicit_stop_is_not_terminal_failure() -> None:
    transport = FakeTransport()
    client = AgentClient(transport, id_factory=id_sequence())
    errors: list[BaseException] = []
    client.set_error_handler(errors.append)
    client.start()

    transport.emit_record({"type": "agent_start"})
    transport.emit_record(
        {
            "type": "auto_retry_start",
            "attempt": 1,
            "maxAttempts": 3,
            "delayMs": 100,
            "errorMessage": "temporary outage",
        }
    )
    client.request_stop()
    assert client.turn_state == TurnState.CANCELLING

    transport.emit_record(
        {
            "type": "auto_retry_end",
            "success": False,
            "attempt": 1,
            "finalError": "Retry cancelled",
        }
    )
    transport.emit_record(
        {
            "type": "agent_end",
            "messages": [
                {
                    "role": "assistant",
                    "content": [],
                    "stopReason": "aborted",
                }
            ],
            "willRetry": False,
        }
    )
    transport.emit_record({"type": "agent_settled"})

    assert client.turn_state == TurnState.IDLE
    assert errors == []


def test_get_messages_is_correlated_and_callback_receives_response() -> None:
    transport = FakeTransport()
    client = AgentClient(transport, id_factory=id_sequence())
    responses: list[dict[str, Any]] = []
    client.start()

    request_id = client.get_messages(responses.append)
    assert request_id == "req-1"
    assert transport.sent[-1] == {"type": "get_messages", "id": "req-1"}

    response = {
        "id": "req-1",
        "type": "response",
        "command": "get_messages",
        "success": True,
        "data": {"messages": [{"role": "user", "content": "hello"}]},
    }
    transport.emit_record(response)

    assert responses == [response]
    assert client.pending_request_ids == ()


def test_transport_state_changes_are_exposed_to_controller() -> None:
    transport = FakeTransport()
    client = AgentClient(transport, id_factory=id_sequence())
    states: list[TransportState] = []
    client.set_transport_state_handler(states.append)

    client.start()
    client.shutdown()

    assert states == [TransportState.READY, TransportState.STOPPED]


def test_stop_clears_queue_before_abort_and_restores_text() -> None:
    transport = FakeTransport()
    client = AgentClient(transport, id_factory=id_sequence())
    cleared: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    client.set_queue_cleared_handler(lambda steering, follow: cleared.append((steering, follow)))
    client.start()

    clear_id = client.request_stop()
    assert clear_id == "req-1"
    assert client.turn_state == TurnState.CANCELLING
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
    assert client.turn_state == TurnState.CANCELLING

    transport.emit_record({"type": "agent_settled"})
    assert client.turn_state == TurnState.IDLE


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

    assert client.turn_state == TurnState.FAILED
    assert errors == [error]
