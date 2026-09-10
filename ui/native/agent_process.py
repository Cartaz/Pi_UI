"""Asynchronous QProcess transport for Pi RPC mode."""

from __future__ import annotations

import codecs
import re
from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer

from core.agent.protocol import JsonlDecoder, JsonlProtocolError, encode_command
from core.agent.runtime import PiLaunchSpec, prepare_runtime_paths
from core.agent.transport import (
    DiagnosticHandler,
    ErrorHandler,
    RecordHandler,
    StateHandler,
    TransportState,
)

_MAX_DIAGNOSTIC_TAIL_CHARS = 2000
_SENSITIVE_ENV_NAME_PARTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[^\s]+")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|authorization|credential)"
    r"([\"']?\s*[:=]\s*[\"']?)([^\"'\s,;}]+)"
)
_URL_CREDENTIAL_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^:/\s]+:)[^@\s]+@")


class QProcessTransportError(RuntimeError):
    """Raised when the native Pi process cannot be operated safely."""


class QProcessAgentTransport(QObject):
    """Qt-owned, non-blocking process transport for one Pi RPC runtime."""

    def __init__(
        self,
        launch_spec: PiLaunchSpec,
        *,
        startup_timeout_ms: int = 10_000,
        shutdown_timeout_ms: int = 5_000,
        max_record_bytes: int = 8 * 1024 * 1024,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if startup_timeout_ms <= 0 or shutdown_timeout_ms <= 0:
            raise ValueError("process timeouts must be positive")
        if max_record_bytes <= 0:
            raise ValueError("max_record_bytes must be positive")

        self._spec = launch_spec
        self._startup_timeout_ms = startup_timeout_ms
        self._shutdown_timeout_ms = shutdown_timeout_ms
        self._max_record_bytes = max_record_bytes
        self._state = TransportState.STOPPED
        self._decoder = JsonlDecoder(max_record_bytes=max_record_bytes)
        self._stderr_decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._stderr_tail = ""
        self._redaction_values = _sensitive_environment_values(self._spec.environment)

        self._record_handler: RecordHandler = lambda _record: None
        self._diagnostic_handler: DiagnosticHandler = lambda _text: None
        self._error_handler: ErrorHandler = lambda _error: None
        self._state_handler: StateHandler = lambda _state: None

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self._process.started.connect(self._on_started)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.errorOccurred.connect(self._on_process_error)
        self._process.finished.connect(self._on_finished)

        self._startup_timer = QTimer(self)
        self._startup_timer.setSingleShot(True)
        self._startup_timer.timeout.connect(self._on_startup_timeout)

        self._shutdown_timer = QTimer(self)
        self._shutdown_timer.setSingleShot(True)
        self._shutdown_timer.timeout.connect(self._force_kill)

    @property
    def state(self) -> TransportState:
        return self._state

    def set_record_handler(self, handler: RecordHandler) -> None:
        self._record_handler = handler

    def set_diagnostic_handler(self, handler: DiagnosticHandler) -> None:
        self._diagnostic_handler = handler

    def set_error_handler(self, handler: ErrorHandler) -> None:
        self._error_handler = handler

    def set_state_handler(self, handler: StateHandler) -> None:
        self._state_handler = handler

    def start(self) -> None:
        if self._process.state() != QProcess.ProcessState.NotRunning:
            raise QProcessTransportError("Pi process is already running")
        if self._state in {
            TransportState.STARTING,
            TransportState.READY,
            TransportState.STOPPING,
        }:
            raise QProcessTransportError(f"cannot start transport while {self._state}")

        prepare_runtime_paths(self._spec.paths)
        self._decoder = JsonlDecoder(max_record_bytes=self._max_record_bytes)
        self._stderr_decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._stderr_tail = ""
        self._redaction_values = _sensitive_environment_values(self._spec.environment)

        environment = QProcessEnvironment()
        for key, value in self._spec.environment.items():
            environment.insert(key, value)

        self._process.setProgram(self._spec.executable)
        self._process.setArguments(list(self._spec.arguments))
        self._process.setWorkingDirectory(str(self._spec.working_directory))
        self._process.setProcessEnvironment(environment)

        self._set_state(TransportState.STARTING)
        self._startup_timer.start(self._startup_timeout_ms)
        self._process.start()

    def send(self, command: Mapping[str, Any]) -> None:
        if self._state != TransportState.READY:
            raise QProcessTransportError(
                f"cannot send RPC command while transport is {self._state}"
            )
        data = encode_command(command)
        written = self._process.write(data)
        if written < 0:
            raise QProcessTransportError(
                f"failed to write Pi stdin: {self._process.errorString()}"
            )

    def stop(self) -> None:
        self._startup_timer.stop()
        if self._process.state() == QProcess.ProcessState.NotRunning:
            if self._state != TransportState.FAILED:
                self._set_state(TransportState.STOPPED)
            return

        self._set_state(TransportState.STOPPING)
        self._process.closeWriteChannel()
        self._process.terminate()
        self._shutdown_timer.start(self._shutdown_timeout_ms)

    def _on_started(self) -> None:
        self._startup_timer.stop()
        self._set_state(TransportState.READY)

    def _on_stdout(self) -> None:
        chunk = bytes(self._process.readAllStandardOutput())
        if not chunk:
            return
        try:
            records = self._decoder.feed(chunk)
        except JsonlProtocolError as exc:
            self._fail(exc, kill_process=True)
            return
        for record in records:
            self._record_handler(record)

    def _on_stderr(self) -> None:
        chunk = bytes(self._process.readAllStandardError())
        if not chunk:
            return
        text = self._stderr_decoder.decode(chunk, final=False)
        if text:
            self._record_stderr(text)

    def _on_process_error(self, process_error: QProcess.ProcessError) -> None:
        if self._state in {TransportState.STOPPING, TransportState.FAILED}:
            return
        self._fail(
            QProcessTransportError(
                f"QProcess error {process_error.name}: {self._process.errorString()}"
            ),
            kill_process=False,
        )

    def _on_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        self._startup_timer.stop()
        self._shutdown_timer.stop()
        self._flush_stderr()

        if self._state != TransportState.STOPPING:
            try:
                self._decoder.finish()
            except JsonlProtocolError as exc:
                self._fail(exc, kill_process=False)
                return

        if self._state == TransportState.STOPPING:
            self._set_state(TransportState.STOPPED)
            return
        if self._state == TransportState.FAILED:
            return
        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            self._set_state(TransportState.STOPPED)
            return

        message = (
            f"Pi process exited unexpectedly: code={exit_code}, status={exit_status.name}"
        )
        diagnostic = self._stderr_tail.strip()
        if diagnostic:
            message = f"{message}; stderr: {diagnostic}"
        self._fail(QProcessTransportError(message), kill_process=False)

    def _on_startup_timeout(self) -> None:
        if self._state != TransportState.STARTING:
            return
        self._fail(
            QProcessTransportError(
                f"Pi process did not start within {self._startup_timeout_ms} ms"
            ),
            kill_process=True,
        )

    def _force_kill(self) -> None:
        if self._process.state() == QProcess.ProcessState.NotRunning:
            return
        self._process.kill()

    def _flush_stderr(self) -> None:
        chunk = bytes(self._process.readAllStandardError())
        text = self._stderr_decoder.decode(chunk, final=True)
        if text:
            self._record_stderr(text)

    def _record_stderr(self, text: str) -> None:
        sanitized = _sanitize_process_diagnostic(text, self._redaction_values)
        if not sanitized:
            return
        self._stderr_tail = (self._stderr_tail + sanitized)[-_MAX_DIAGNOSTIC_TAIL_CHARS:]
        self._diagnostic_handler(sanitized)

    def _fail(self, error: BaseException, *, kill_process: bool) -> None:
        self._startup_timer.stop()
        self._shutdown_timer.stop()
        self._set_state(TransportState.FAILED)
        self._error_handler(error)
        if kill_process and self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()

    def _set_state(self, state: TransportState) -> None:
        if state == self._state:
            return
        self._state = state
        self._state_handler(state)


def _sensitive_environment_values(environment: Mapping[str, str]) -> tuple[str, ...]:
    values = {
        value
        for key, value in environment.items()
        if value
        and len(value) >= 4
        and any(part in key.upper() for part in _SENSITIVE_ENV_NAME_PARTS)
    }
    return tuple(sorted(values, key=len, reverse=True))


def _sanitize_process_diagnostic(text: str, redaction_values: tuple[str, ...]) -> str:
    sanitized = text
    for value in redaction_values:
        sanitized = sanitized.replace(value, "<redacted>")
    sanitized = _BEARER_RE.sub("Bearer <redacted>", sanitized)
    sanitized = _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}<redacted>",
        sanitized,
    )
    sanitized = _URL_CREDENTIAL_RE.sub(r"\1<redacted>@", sanitized)
    return sanitized
