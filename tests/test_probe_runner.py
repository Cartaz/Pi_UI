from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from core.preflight import CommandProbe, CommandProbeResult
from ui.native.probe_runner import QtProbeRunner


def _application() -> QApplication:
    instance = QApplication.instance()
    if instance is not None:
        return instance
    return QApplication([])


def _environment(tmp_path: Path) -> tuple[tuple[str, str], ...]:
    return (
        ("HOME", str(tmp_path)),
        ("LANG", "C.UTF-8"),
        ("PATH", os.environ.get("PATH", "/usr/bin:/bin")),
    )


def test_probe_runner_reports_stdout_and_runs_sequentially(tmp_path: Path) -> None:
    app = _application()
    runner = QtProbeRunner()
    loop = QEventLoop()
    results: list[CommandProbeResult] = []
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    timed_out = False

    probes = (
        CommandProbe(
            "one",
            "One",
            sys.executable,
            ("-c", "print('first')"),
            timeout_ms=1_000,
        ),
        CommandProbe(
            "two",
            "Two",
            sys.executable,
            ("-c", "import sys; print('second', file=sys.stderr)"),
            timeout_ms=1_000,
        ),
    )

    def on_watchdog() -> None:
        nonlocal timed_out
        timed_out = True
        loop.quit()

    watchdog.timeout.connect(on_watchdog)
    watchdog.start(3_000)
    runner.start(
        probes,
        environment=_environment(tmp_path),
        result_handler=results.append,
        finished_handler=loop.quit,
    )
    loop.exec()
    watchdog.stop()
    app.processEvents()

    assert timed_out is False
    assert [item.probe_id for item in results] == ["one", "two"]
    assert results[0].exit_code == 0
    assert results[0].stdout.strip() == "first"
    assert results[1].exit_code == 0
    assert results[1].stderr.strip() == "second"
    assert runner.running is False


def test_probe_runner_marks_timeout_without_blocking_event_loop(tmp_path: Path) -> None:
    app = _application()
    runner = QtProbeRunner()
    loop = QEventLoop()
    results: list[CommandProbeResult] = []
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    timed_out = False

    probe = CommandProbe(
        "slow",
        "Slow",
        sys.executable,
        ("-c", "import time; time.sleep(5)"),
        timeout_ms=30,
    )

    def on_watchdog() -> None:
        nonlocal timed_out
        timed_out = True
        loop.quit()

    watchdog.timeout.connect(on_watchdog)
    watchdog.start(3_000)
    runner.start(
        (probe,),
        environment=_environment(tmp_path),
        result_handler=results.append,
        finished_handler=loop.quit,
    )
    loop.exec()
    watchdog.stop()
    app.processEvents()

    assert timed_out is False
    assert len(results) == 1
    assert results[0].probe_id == "slow"
    assert results[0].timed_out is True
    assert runner.running is False


def test_probe_runner_cancel_suppresses_late_result_and_finished_callbacks(
    tmp_path: Path,
) -> None:
    app = _application()
    runner = QtProbeRunner()
    loop = QEventLoop()
    results: list[CommandProbeResult] = []
    finished: list[bool] = []
    watchdog = QTimer()
    watchdog.setSingleShot(True)

    probe = CommandProbe(
        "cancel-me",
        "Cancel",
        sys.executable,
        ("-c", "import time; time.sleep(5)"),
        timeout_ms=2_000,
    )

    runner.start(
        (probe,),
        environment=_environment(tmp_path),
        result_handler=results.append,
        finished_handler=lambda: finished.append(True),
    )
    QTimer.singleShot(30, runner.cancel)
    QTimer.singleShot(150, loop.quit)
    watchdog.timeout.connect(loop.quit)
    watchdog.start(2_000)
    loop.exec()
    watchdog.stop()
    app.processEvents()

    assert runner.running is False
    assert results == []
    assert finished == []
