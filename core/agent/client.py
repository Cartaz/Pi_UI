"""High-level Pi RPC client state independent from Qt presentation code."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import uuid4

from .transport import AgentTransport, TransportState

JsonObject = dict[str, Any]
ResponseCallback = Callable[[JsonObject], None]
RecordHandler = Callable[[JsonObject], None]
QueueClearedHandler = Callable[[tuple[str, ...], tuple[str, ...]], None]
TurnStateHandler = Callable[["TurnState"], None]
TransportStateHandler = Callable[[TransportState], None]
ErrorHandler = Callable[[BaseException], None]
IdFactory = Callable[[], str]


class AgentClientError(RuntimeError):
    """Raised when a Pi RPC command cannot be represented safely."""


class TurnState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    CANCELLING = "cancelling"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PendingRequest:
    request_id: str
    command: str
    callback: ResponseCallback | None = None


class AgentClient:
    """Own request correlation and turn lifecycle for one Pi RPC session."""

    def __init__(
        self,
        transport: AgentTransport,
        *,
        id_factory: IdFactory | None = None,
    ) -> None:
        self._transport = transport
        self._id_factory = id_factory or (lambda: uuid4().hex)
        self._pending: dict[str, PendingRequest] = {}
        self._turn_state = TurnState.IDLE
        self._event_handler: RecordHandler = lambda _record: None
        self._response_handler: RecordHandler = lambda _record: None
        self._queue_cleared_handler: QueueClearedHandler = (
            lambda _steering, _follow_up: None
        )
        self._turn_state_handler: TurnStateHandler = lambda _state: None
        self._transport_state_handler: TransportStateHandler = lambda _state: None
        self._error_handler: ErrorHandler = lambda _error: None

        transport.set_record_handler(self._on_record)
        transport.set_error_handler(self._on_transport_error)
        transport.set_state_handler(self._on_transport_state)

    @property
    def transport_state(self) -> TransportState:
        return self._transport.state

    @property
    def turn_state(self) -> TurnState:
        return self._turn_state

    @property
    def pending_request_ids(self) -> tuple[str, ...]:
        return tuple(self._pending)

    def set_event_handler(self, handler: RecordHandler) -> None:
        self._event_handler = handler

    def set_response_handler(self, handler: RecordHandler) -> None:
        self._response_handler = handler

    def set_queue_cleared_handler(self, handler: QueueClearedHandler) -> None:
        self._queue_cleared_handler = handler

    def set_turn_state_handler(self, handler: TurnStateHandler) -> None:
        self._turn_state_handler = handler

    def set_transport_state_handler(self, handler: TransportStateHandler) -> None:
        self._transport_state_handler = handler

    def set_error_handler(self, handler: ErrorHandler) -> None:
        self._error_handler = handler

    def start(self) -> None:
        self._transport.start()

    def shutdown(self) -> None:
        self._transport.stop()

    def prompt(
        self,
        message: str,
        *,
        streaming_behavior: str | None = None,
    ) -> str:
        command: JsonObject = {"type": "prompt", "message": _require_message(message)}
        if streaming_behavior is not None:
            if streaming_behavior not in {"steer", "followUp"}:
                raise AgentClientError(
                    "streaming_behavior must be 'steer' or 'followUp'"
                )
            command["streamingBehavior"] = streaming_behavior
        return self._send(command)

    def steer(self, message: str) -> str:
        return self._send({"type": "steer", "message": _require_message(message)})

    def follow_up(self, message: str) -> str:
        return self._send({"type": "follow_up", "message": _require_message(message)})

    def get_state(self, callback: ResponseCallback | None = None) -> str:
        return self._send({"type": "get_state"}, callback=callback)

    def get_messages(self, callback: ResponseCallback | None = None) -> str:
        return self._send({"type": "get_messages"}, callback=callback)

    def request_stop(self) -> str:
        """Clear queued input first, then abort the active operation.

        Pi documents this ordering for interactive Esc semantics: ``abort`` by
        itself can continue queued messages, while ``clear_queue`` returns the
        text so the client can restore it to the composer.
        """

        self._set_turn_state(TurnState.CANCELLING)
        return self._send({"type": "clear_queue"}, callback=self._after_clear_queue)

    def _send(
        self,
        command: Mapping[str, Any],
        *,
        callback: ResponseCallback | None = None,
    ) -> str:
        command_type = command.get("type")
        if not isinstance(command_type, str) or not command_type:
            raise AgentClientError("RPC command requires a non-empty string type")

        request_id = self._next_request_id()
        payload = dict(command)
        payload["id"] = request_id
        self._pending[request_id] = PendingRequest(
            request_id=request_id,
            command=command_type,
            callback=callback,
        )
        try:
            self._transport.send(payload)
        except BaseException:
            self._pending.pop(request_id, None)
            raise
        return request_id

    def _next_request_id(self) -> str:
        request_id = self._id_factory()
        if not isinstance(request_id, str) or not request_id:
            raise AgentClientError("id_factory must return a non-empty string")
        if request_id in self._pending:
            raise AgentClientError(f"duplicate pending request id: {request_id}")
        return request_id

    def _on_record(self, record: JsonObject) -> None:
        if record.get("type") == "response":
            self._on_response(record)
            return

        event_type = record.get("type")
        if event_type in {"agent_start", "turn_start"}:
            self._set_turn_state(TurnState.RUNNING)
        elif event_type == "agent_settled":
            self._set_turn_state(TurnState.IDLE)
        self._event_handler(record)

    def _on_response(self, response: JsonObject) -> None:
        request_id = response.get("id")
        pending = self._pending.pop(request_id, None) if isinstance(request_id, str) else None

        self._response_handler(response)
        if pending and pending.callback:
            pending.callback(response)

    def _after_clear_queue(self, response: JsonObject) -> None:
        steering: tuple[str, ...] = ()
        follow_up: tuple[str, ...] = ()
        data = response.get("data")
        if response.get("success") is True and isinstance(data, dict):
            steering = _string_tuple(data.get("steering"))
            follow_up = _string_tuple(data.get("followUp"))
        self._queue_cleared_handler(steering, follow_up)

        self._send({"type": "abort"}, callback=self._after_abort)

    def _after_abort(self, response: JsonObject) -> None:
        if response.get("success") is False:
            self._set_turn_state(TurnState.FAILED)
            self._error_handler(AgentClientError("Pi rejected abort command"))

    def _on_transport_error(self, error: BaseException) -> None:
        if self._turn_state != TurnState.IDLE:
            self._set_turn_state(TurnState.FAILED)
        self._error_handler(error)

    def _on_transport_state(self, state: TransportState) -> None:
        if state == TransportState.FAILED:
            self._set_turn_state(TurnState.FAILED)
        elif state == TransportState.STOPPED and self._turn_state != TurnState.FAILED:
            self._set_turn_state(TurnState.IDLE)
        self._transport_state_handler(state)

    def _set_turn_state(self, state: TurnState) -> None:
        if state == self._turn_state:
            return
        self._turn_state = state
        self._turn_state_handler(state)


def _require_message(message: str) -> str:
    if not isinstance(message, str) or not message.strip():
        raise AgentClientError("message must be a non-empty string")
    return message


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))
