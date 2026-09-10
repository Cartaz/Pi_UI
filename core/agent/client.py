"""High-level Pi RPC client state independent from Qt presentation code."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import uuid4

from .deadlines import DeadlineHandle, DeadlineScheduler
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


class AgentRequestTimeoutError(AgentClientError):
    """Raised when Pi does not acknowledge one correlated RPC request in time."""

    def __init__(self, request_id: str, command: str, timeout_ms: int) -> None:
        self.request_id = request_id
        self.command = command
        self.timeout_ms = timeout_ms
        super().__init__(
            f"Pi did not acknowledge {command!r} request {request_id!r} "
            f"within {timeout_ms} ms"
        )


class AgentInactivityTimeoutError(AgentClientError):
    """Raised as a non-destructive watchdog when an active turn is silent."""

    def __init__(self, timeout_ms: int) -> None:
        self.timeout_ms = timeout_ms
        super().__init__(f"Pi turn produced no RPC activity for {timeout_ms} ms")


class AgentTurnFailedError(AgentClientError):
    """Raised when an accepted Pi turn reaches a terminal model failure."""

    def __init__(self, message: str, *, attempts: int | None = None) -> None:
        self.attempts = attempts
        self.detail = message
        if attempts is None:
            rendered = f"Pi model request failed: {message}"
        else:
            rendered = f"Pi model request failed after {attempts} attempts: {message}"
        super().__init__(rendered)


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
    """Own request correlation and turn lifecycle for one Pi RPC session.

    Request deadlines only describe whether the RPC acknowledgement arrived;
    they never imply that a command was not executed. Inactivity deadlines are
    a watchdog only: they notify the caller without killing Pi or retrying work.
    """

    _TURN_COMMANDS = frozenset({"prompt", "steer", "follow_up", "clear_queue", "abort"})

    def __init__(
        self,
        transport: AgentTransport,
        *,
        id_factory: IdFactory | None = None,
        deadline_scheduler: DeadlineScheduler | None = None,
        request_timeout_ms: int | None = None,
        inactivity_timeout_ms: int | None = None,
    ) -> None:
        if deadline_scheduler is None and (
            request_timeout_ms is not None or inactivity_timeout_ms is not None
        ):
            raise ValueError("deadline_scheduler is required when client timeouts are enabled")
        for name, value in (
            ("request_timeout_ms", request_timeout_ms),
            ("inactivity_timeout_ms", inactivity_timeout_ms),
        ):
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value <= 0
            ):
                raise ValueError(f"{name} must be a positive integer or None")

        self._transport = transport
        self._id_factory = id_factory or (lambda: uuid4().hex)
        self._deadline_scheduler = deadline_scheduler
        self._request_timeout_ms = request_timeout_ms
        self._inactivity_timeout_ms = inactivity_timeout_ms
        self._pending: dict[str, PendingRequest] = {}
        self._request_deadlines: dict[str, DeadlineHandle] = {}
        self._inactivity_deadline: DeadlineHandle | None = None
        self._turn_state = TurnState.IDLE
        self._auto_retry_in_progress = False
        self._event_handler: RecordHandler = lambda _record: None
        self._response_handler: RecordHandler = lambda _record: None
        self._queue_cleared_handler: QueueClearedHandler = (
            lambda _steering, _follow_up: None
        )
        self._turn_state_handler: TurnStateHandler = lambda _state: None
        self._transport_state_handler: TransportStateHandler = lambda _state: None
        self._error_handler: ErrorHandler = lambda _error: None
        self._request_timeout_handler: Callable[[AgentRequestTimeoutError], None] = (
            lambda error: self._error_handler(error)
        )
        self._inactivity_timeout_handler: Callable[[AgentInactivityTimeoutError], None] = (
            lambda error: self._error_handler(error)
        )

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

    def set_request_timeout_handler(
        self,
        handler: Callable[[AgentRequestTimeoutError], None],
    ) -> None:
        self._request_timeout_handler = handler

    def set_inactivity_timeout_handler(
        self,
        handler: Callable[[AgentInactivityTimeoutError], None],
    ) -> None:
        self._inactivity_timeout_handler = handler

    def start(self) -> None:
        self._turn_state_handler(self._turn_state)
        self._transport.start()

    def shutdown(self) -> None:
        self._cancel_all_deadlines()
        self._pending.clear()
        self._auto_retry_in_progress = False
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

    def get_entries(self, callback: ResponseCallback | None = None) -> str:
        return self._send({"type": "get_entries"}, callback=callback)

    def fork(self, entry_id: str, callback: ResponseCallback | None = None) -> str:
        if not isinstance(entry_id, str) or not entry_id:
            raise AgentClientError("entry_id must be a non-empty string")
        return self._send({"type": "fork", "entryId": entry_id}, callback=callback)

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
        self._arm_request_deadline(request_id)
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
            self._note_activity()
            return

        event_type = record.get("type")
        if event_type in {"agent_start", "turn_start"}:
            self._set_turn_state(TurnState.RUNNING)
        elif event_type == "auto_retry_start":
            self._auto_retry_in_progress = True
        elif event_type == "auto_retry_end":
            self._handle_auto_retry_end(record)
        elif event_type == "agent_end":
            self._handle_agent_end(record)
        elif event_type == "agent_settled":
            self._auto_retry_in_progress = False
            if self._turn_state != TurnState.FAILED:
                self._set_turn_state(TurnState.IDLE)
        self._note_activity()
        self._event_handler(record)

    def _handle_auto_retry_end(self, event: JsonObject) -> None:
        self._auto_retry_in_progress = False
        if event.get("success") is not False or self._turn_state == TurnState.CANCELLING:
            return
        attempt = event.get("attempt")
        attempts = attempt if isinstance(attempt, int) and not isinstance(attempt, bool) else None
        final_error = event.get("finalError")
        detail = final_error if isinstance(final_error, str) and final_error else "Unknown model error"
        self._set_turn_state(TurnState.FAILED)
        self._error_handler(AgentTurnFailedError(detail, attempts=attempts))

    def _handle_agent_end(self, event: JsonObject) -> None:
        if (
            event.get("willRetry") is not False
            or self._auto_retry_in_progress
            or self._turn_state in {TurnState.CANCELLING, TurnState.FAILED}
        ):
            return
        detail = _terminal_agent_error(event)
        if detail is None:
            return
        self._set_turn_state(TurnState.FAILED)
        self._error_handler(AgentTurnFailedError(detail))

    def _on_response(self, response: JsonObject) -> None:
        request_id = response.get("id")
        pending = self._pending.pop(request_id, None) if isinstance(request_id, str) else None
        if isinstance(request_id, str):
            self._cancel_request_deadline(request_id)

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

    def _arm_request_deadline(self, request_id: str) -> None:
        scheduler = self._deadline_scheduler
        timeout_ms = self._request_timeout_ms
        if scheduler is None or timeout_ms is None:
            return
        self._cancel_request_deadline(request_id)
        self._request_deadlines[request_id] = scheduler.call_later(
            timeout_ms,
            lambda: self._on_request_timeout(request_id),
        )

    def _cancel_request_deadline(self, request_id: str) -> None:
        handle = self._request_deadlines.pop(request_id, None)
        if handle is not None:
            handle.cancel()

    def _on_request_timeout(self, request_id: str) -> None:
        self._request_deadlines.pop(request_id, None)
        pending = self._pending.pop(request_id, None)
        if pending is None or self._request_timeout_ms is None:
            return
        if pending.command in self._TURN_COMMANDS:
            self._set_turn_state(TurnState.FAILED)
        self._request_timeout_handler(
            AgentRequestTimeoutError(
                request_id=request_id,
                command=pending.command,
                timeout_ms=self._request_timeout_ms,
            )
        )

    def _note_activity(self) -> None:
        if self._turn_state in {TurnState.RUNNING, TurnState.CANCELLING}:
            self._arm_inactivity_deadline()

    def _arm_inactivity_deadline(self) -> None:
        self._cancel_inactivity_deadline()
        scheduler = self._deadline_scheduler
        timeout_ms = self._inactivity_timeout_ms
        if scheduler is None or timeout_ms is None:
            return
        self._inactivity_deadline = scheduler.call_later(
            timeout_ms,
            self._on_inactivity_timeout,
        )

    def _cancel_inactivity_deadline(self) -> None:
        handle = self._inactivity_deadline
        self._inactivity_deadline = None
        if handle is not None:
            handle.cancel()

    def _on_inactivity_timeout(self) -> None:
        self._inactivity_deadline = None
        timeout_ms = self._inactivity_timeout_ms
        if timeout_ms is None or self._turn_state not in {
            TurnState.RUNNING,
            TurnState.CANCELLING,
        }:
            return
        self._inactivity_timeout_handler(AgentInactivityTimeoutError(timeout_ms))

    def _cancel_all_deadlines(self) -> None:
        for handle in tuple(self._request_deadlines.values()):
            handle.cancel()
        self._request_deadlines.clear()
        self._cancel_inactivity_deadline()

    def _on_transport_error(self, error: BaseException) -> None:
        self._cancel_all_deadlines()
        self._pending.clear()
        self._auto_retry_in_progress = False
        if self._turn_state != TurnState.IDLE:
            self._set_turn_state(TurnState.FAILED)
        self._error_handler(error)

    def _on_transport_state(self, state: TransportState) -> None:
        if state == TransportState.FAILED:
            self._cancel_all_deadlines()
            self._pending.clear()
            self._auto_retry_in_progress = False
            self._set_turn_state(TurnState.FAILED)
        elif state == TransportState.STOPPED:
            self._cancel_all_deadlines()
            self._pending.clear()
            self._auto_retry_in_progress = False
            if self._turn_state != TurnState.FAILED:
                self._set_turn_state(TurnState.IDLE)
        self._transport_state_handler(state)

    def _set_turn_state(self, state: TurnState) -> None:
        if state == self._turn_state:
            return
        self._turn_state = state
        if state in {TurnState.RUNNING, TurnState.CANCELLING}:
            self._arm_inactivity_deadline()
        else:
            self._cancel_inactivity_deadline()
        self._turn_state_handler(state)


def _terminal_agent_error(event: JsonObject) -> str | None:
    messages = event.get("messages")
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        if message.get("stopReason") != "error":
            return None
        error_message = message.get("errorMessage")
        if isinstance(error_message, str) and error_message:
            return error_message
        return "Unknown model error"
    return None


def _require_message(message: str) -> str:
    if not isinstance(message, str) or not message.strip():
        raise AgentClientError("message must be a non-empty string")
    return message


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))