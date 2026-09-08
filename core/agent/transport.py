"""Presentation-independent transport contract for a Pi RPC process."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Any, Protocol

JsonObject = dict[str, Any]
RecordHandler = Callable[[JsonObject], None]
ErrorHandler = Callable[[BaseException], None]
StateHandler = Callable[["TransportState"], None]


class TransportState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"
    FAILED = "failed"


class AgentTransport(Protocol):
    """Minimal asynchronous byte-transport boundary used by the controller.

    The Qt implementation belongs in ``ui/native``. Core code depends only on
    this protocol, so tests can use deterministic in-memory transports.
    """

    @property
    def state(self) -> TransportState: ...

    def set_record_handler(self, handler: RecordHandler) -> None: ...

    def set_error_handler(self, handler: ErrorHandler) -> None: ...

    def set_state_handler(self, handler: StateHandler) -> None: ...

    def start(self) -> None: ...

    def send(self, command: Mapping[str, Any]) -> None: ...

    def stop(self) -> None: ...
