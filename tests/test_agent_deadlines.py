from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from core.agent.client import (
    AgentClient,
    AgentInactivityTimeoutError,
    AgentRequestTimeoutError,
    TurnState,
)
from core.agent.transport import TransportState


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
        raise AssertionError(f"no active deadline scheduled for {delay_ms} ms")


class FakeTransport:
    def __init__(self) -> None:
        self._state = TransportState.STOPPED
        self.sent: list[dict[str, Any]] = []
        self._record_handler: Callable[[dict[str, Any]], None] = lambda _record: None
        self._error_handler: Callable[[BaseException], None] = lambda _error: None
        self._state_handler: Callable[[TransportState], None] = lambda _state: None

    @property
    def state(self) -> TransportState:
        return self._state

    def set_record_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        self._record_handler = handler

    def set_diagnostic_handler(self, _handler: Callable[[str], None]) -> None:
        return

    def set_error_handler(self, handler: Callable[[BaseException], None]) -> None:
        self._error_handler = handler

    def set_state_handler(self, handler: Callable[[TransportState], None]) -> None:
        self._state_handler = handler

    def start(self) -> None:
        self._state = TransportState.READY
        self._state_handler(self._state)

    def send(self, command: Mapping[str, Any]) -> None:
        if self._state != TransportState.READY:
            raise RuntimeError("transport not ready")
        self.sent.append(dict(command))

    def stop(self) -> None:
        self._state = TransportState.STOPPED
        self._state_handler(self._state)

    def emit(self, record: dict[str, Any]) -> None:
        self._record_handler(record)


def _ids() -> Callable[[], str]:
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"req-{counter}"

    return next_id


def _client(
    transport: FakeTransport,
    scheduler: ManualScheduler,
) -> AgentClient:
    return AgentClient(
        transport,
        id_factory=_ids(),
        deadline_scheduler=scheduler,
        request_timeout_ms=1_000,
        inactivity_timeout_ms=5_000,
    )


def test_prompt_ack_timeout_is_correlated_and_never_retried() -> None:
    transport = FakeTransport()
    scheduler = ManualScheduler()
    client = _client(transport, scheduler)
    timeouts: list[AgentRequestTimeoutError] = []
    client.set_request_timeout_handler(timeouts.append)
    client.start()

    request_id = client.prompt("hello")
    assert request_id == "req-1"
    assert len(transport.sent) == 1

    scheduler.latest(1_000).fire()

    assert len(timeouts) == 1
    assert timeouts[0].request_id == "req-1"
    assert timeouts[0].command == "prompt"
    assert client.pending_request_ids == ()
    assert client.turn_state == TurnState.FAILED
    assert len(transport.sent) == 1

    transport.emit(
        {
            "id": "req-1",
            "type": "response",
            "command": "prompt",
            "success": True,
        }
    )
    assert len(transport.sent) == 1


def test_response_cancels_request_deadline() -> None:
    transport = FakeTransport()
    scheduler = ManualScheduler()
    client = _client(transport, scheduler)
    timeouts: list[AgentRequestTimeoutError] = []
    client.set_request_timeout_handler(timeouts.append)
    client.start()

    request_id = client.get_state()
    handle = scheduler.latest(1_000)
    transport.emit(
        {
            "id": request_id,
            "type": "response",
            "command": "get_state",
            "success": True,
            "data": {},
        }
    )
    handle.fire()

    assert handle.cancelled is True
    assert timeouts == []
    assert client.pending_request_ids == ()


def test_inactivity_watchdog_notifies_without_killing_or_retrying() -> None:
    transport = FakeTransport()
    scheduler = ManualScheduler()
    client = _client(transport, scheduler)
    timeouts: list[AgentInactivityTimeoutError] = []
    client.set_inactivity_timeout_handler(timeouts.append)
    client.start()

    transport.emit({"type": "agent_start"})
    assert client.turn_state == TurnState.RUNNING
    first = scheduler.latest(5_000)
    first.fire()

    assert len(timeouts) == 1
    assert timeouts[0].timeout_ms == 5_000
    assert client.turn_state == TurnState.RUNNING
    assert transport.state == TransportState.READY
    assert transport.sent == []

    transport.emit(
        {
            "type": "message_update",
            "assistantMessageEvent": {
                "type": "text_delta",
                "contentIndex": 0,
                "delta": "still alive",
            },
        }
    )
    second = scheduler.latest(5_000)
    assert second is not first

    transport.emit({"type": "agent_settled"})
    assert client.turn_state == TurnState.IDLE
    assert second.cancelled is True


def test_shutdown_cancels_request_and_inactivity_deadlines() -> None:
    transport = FakeTransport()
    scheduler = ManualScheduler()
    client = _client(transport, scheduler)
    client.start()

    client.get_state()
    request_handle = scheduler.latest(1_000)
    transport.emit({"type": "agent_start"})
    inactivity_handle = scheduler.latest(5_000)

    client.shutdown()

    assert request_handle.cancelled is True
    assert inactivity_handle.cancelled is True
    assert client.pending_request_ids == ()
    assert transport.state == TransportState.STOPPED
