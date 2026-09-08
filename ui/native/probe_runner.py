"""Asynchronous QProcess runner for harmless preflight probes."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer

from core.preflight import CommandProbe, CommandProbeResult

ProbeResultHandler = Callable[[CommandProbeResult], None]
FinishedHandler = Callable[[], None]


class QtProbeRunner(QObject):
    """Run command probes sequentially without a shell or GUI-thread blocking."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._queue: list[CommandProbe] = []
        self._environment: tuple[tuple[str, str], ...] = ()
        self._result_handler: ProbeResultHandler = lambda _result: None
        self._finished_handler: FinishedHandler = lambda: None
        self._process: QProcess | None = None
        self._probe: CommandProbe | None = None
        self._stdout = bytearray()
        self._stderr = bytearray()
        self._timed_out = False
        self._reported = False
        self._cancelled = False

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    @property
    def running(self) -> bool:
        return self._process is not None or bool(self._queue)

    def start(
        self,
        probes: tuple[CommandProbe, ...],
        *,
        environment: tuple[tuple[str, str], ...],
        result_handler: ProbeResultHandler,
        finished_handler: FinishedHandler,
    ) -> None:
        if self.running:
            raise RuntimeError("preflight probe runner is already active")
        self._queue = list(probes)
        self._environment = tuple(environment)
        self._result_handler = result_handler
        self._finished_handler = finished_handler
        self._cancelled = False
        self._start_next()

    def cancel(self) -> None:
        self._queue.clear()
        self._timer.stop()
        self._cancelled = True
        self._reported = True
        self._result_handler = lambda _result: None
        self._finished_handler = lambda: None
        process = self._process
        self._process = None
        self._probe = None
        if process is None:
            return
        if process.state() == QProcess.ProcessState.NotRunning:
            process.deleteLater()
            return
        process.finished.connect(process.deleteLater)
        process.kill()

    def _start_next(self) -> None:
        if self._cancelled:
            self._process = None
            self._probe = None
            return
        if not self._queue:
            self._process = None
            self._probe = None
            self._finished_handler()
            return

        probe = self._queue.pop(0)
        process = QProcess(self)
        environment = QProcessEnvironment()
        for key, value in self._environment:
            environment.insert(key, value)
        process.setProcessEnvironment(environment)
        process.setProgram(probe.executable)
        process.setArguments(list(probe.arguments))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)
        process.started.connect(lambda: self._timer.start(probe.timeout_ms))
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)

        self._process = process
        self._probe = probe
        self._stdout = bytearray()
        self._stderr = bytearray()
        self._timed_out = False
        self._reported = False
        process.start()

    def _read_stdout(self) -> None:
        process = self._process
        if process is not None:
            self._stdout.extend(bytes(process.readAllStandardOutput()))

    def _read_stderr(self) -> None:
        process = self._process
        if process is not None:
            self._stderr.extend(bytes(process.readAllStandardError()))

    def _on_timeout(self) -> None:
        process = self._process
        if process is None or self._cancelled:
            return
        self._timed_out = True
        if process.state() != QProcess.ProcessState.NotRunning:
            process.kill()

    def _on_error(self, error: QProcess.ProcessError) -> None:
        if self._reported or self._cancelled:
            return
        if error not in {
            QProcess.ProcessError.FailedToStart,
            QProcess.ProcessError.Crashed,
        }:
            return
        process = self._process
        if process is None:
            return
        if error == QProcess.ProcessError.FailedToStart:
            self._report_current(
                exit_code=None,
                start_error=process.errorString() or "probe failed to start",
            )
            self._dispose_and_continue()

    def _on_finished(self, exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        if self._reported or self._cancelled:
            return
        self._read_stdout()
        self._read_stderr()
        self._report_current(exit_code=exit_code)
        self._dispose_and_continue()

    def _report_current(
        self,
        *,
        exit_code: int | None,
        start_error: str | None = None,
    ) -> None:
        probe = self._probe
        if probe is None or self._reported or self._cancelled:
            return
        self._reported = True
        self._timer.stop()
        result = CommandProbeResult(
            probe_id=probe.probe_id,
            exit_code=exit_code,
            stdout=_decode(self._stdout),
            stderr=_decode(self._stderr),
            timed_out=self._timed_out,
            start_error=start_error,
        )
        self._result_handler(result)

    def _dispose_and_continue(self) -> None:
        process = self._process
        self._process = None
        self._probe = None
        if process is not None:
            process.deleteLater()
        self._start_next()


def _decode(value: bytearray) -> str:
    return bytes(value).decode("utf-8", errors="replace")
