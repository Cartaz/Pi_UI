from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from core.agent.runtime import PiLaunchSpec, PiRuntimePaths
from core.agent.transport import TransportState
from ui.native.agent_process import QProcessAgentTransport


def _application() -> QApplication:
    instance = QApplication.instance()
    if instance is not None:
        return instance
    return QApplication([])


def test_explicit_stop_after_failed_process_reports_stopped(tmp_path: Path) -> None:
    _application()
    script = tmp_path / "exit_one.py"
    script.write_text(
        'import sys\nprint("missing session", file=sys.stderr, flush=True)\nsys.exit(1)\n',
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
        if state == TransportState.FAILED:
            transport.stop()
        elif state == TransportState.STOPPED:
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
    assert len(errors) == 1
    assert "missing session" in str(errors[0])
    assert TransportState.FAILED in states
    assert states[-1] == TransportState.STOPPED
