from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from core.agent.runtime import PiLaunchSpec, PiRuntimePaths
from core.agent.transport import TransportState
from ui.native.agent_process import QProcessAgentTransport


def _application() -> QCoreApplication:
    instance = QCoreApplication.instance()
    if instance is not None:
        return instance
    return QCoreApplication([])


def test_shutdown_escalates_when_child_ignores_terminate(tmp_path: Path) -> None:
    _application()
    script = tmp_path / "ignore_term.py"
    script.write_text(
        """
import signal
import time

signal.signal(signal.SIGTERM, lambda *_args: None)
while True:
    time.sleep(1)
""".lstrip(),
        encoding="utf-8",
    )

    spec = PiLaunchSpec(
        executable=sys.executable,
        arguments=("-u", str(script)),
        environment={
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
        },
        working_directory=tmp_path,
        paths=PiRuntimePaths.for_workspace(tmp_path),
    )
    transport = QProcessAgentTransport(
        spec,
        startup_timeout_ms=2_000,
        shutdown_timeout_ms=50,
    )

    states: list[TransportState] = []
    errors: list[BaseException] = []
    loop = QEventLoop()
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    timed_out = False

    def on_state(state: TransportState) -> None:
        states.append(state)
        if state == TransportState.READY:
            transport.stop()
        elif state in {TransportState.STOPPED, TransportState.FAILED}:
            loop.quit()

    def on_watchdog() -> None:
        nonlocal timed_out
        timed_out = True
        loop.quit()

    transport.set_state_handler(on_state)
    transport.set_error_handler(errors.append)
    watchdog.timeout.connect(on_watchdog)
    watchdog.start(3_000)
    transport.start()
    loop.exec()
    watchdog.stop()

    assert timed_out is False
    assert errors == []
    assert states[0] == TransportState.STARTING
    assert TransportState.READY in states
    assert TransportState.STOPPING in states
    assert states[-1] == TransportState.STOPPED
