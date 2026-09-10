from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from core.agent.runtime import PiLaunchSpec, PiRuntimePaths
from ui.native.agent_process import QProcessAgentTransport


def _application() -> QApplication:
    instance = QApplication.instance()
    if instance is not None:
        return instance
    return QApplication([])


def test_nonzero_exit_surfaces_sanitized_stderr(tmp_path: Path) -> None:
    app = _application()
    paths = PiRuntimePaths.for_workspace(tmp_path)
    secret = "test-secret-value"
    spec = PiLaunchSpec(
        executable=sys.executable,
        arguments=(
            "-c",
            (
                "import sys; "
                "sys.stderr.write('fatal apiKey=test-secret-value "
                "Bearer bearer-token https://user:pass@example.test\\n'); "
                "raise SystemExit(1)"
            ),
        ),
        environment={"TEST_API_KEY": secret, "LANG": "C.UTF-8"},
        working_directory=tmp_path,
        paths=paths,
    )
    transport = QProcessAgentTransport(spec, startup_timeout_ms=2_000)
    errors: list[BaseException] = []
    diagnostics: list[str] = []
    loop = QEventLoop()

    transport.set_diagnostic_handler(diagnostics.append)

    def on_error(error: BaseException) -> None:
        errors.append(error)
        loop.quit()

    transport.set_error_handler(on_error)
    transport.start()
    QTimer.singleShot(3_000, loop.quit)
    loop.exec()
    app.processEvents()

    assert len(errors) == 1
    rendered = str(errors[0])
    assert "code=1" in rendered
    assert "stderr:" in rendered
    assert "fatal" in rendered
    assert secret not in rendered
    assert "bearer-token" not in rendered
    assert "user:pass@" not in rendered
    assert "<redacted>" in rendered

    combined_diagnostics = "".join(diagnostics)
    assert secret not in combined_diagnostics
    assert "bearer-token" not in combined_diagnostics
    assert "user:pass@" not in combined_diagnostics


def test_process_diagnostic_tail_is_bounded(tmp_path: Path) -> None:
    app = _application()
    paths = PiRuntimePaths.for_workspace(tmp_path)
    spec = PiLaunchSpec(
        executable=sys.executable,
        arguments=(
            "-c",
            "import sys; sys.stderr.write('x' * 4000 + 'TAIL'); raise SystemExit(1)",
        ),
        environment={"LANG": "C.UTF-8"},
        working_directory=tmp_path,
        paths=paths,
    )
    transport = QProcessAgentTransport(spec, startup_timeout_ms=2_000)
    errors: list[BaseException] = []
    loop = QEventLoop()

    def on_error(error: BaseException) -> None:
        errors.append(error)
        loop.quit()

    transport.set_error_handler(on_error)
    transport.start()
    QTimer.singleShot(3_000, loop.quit)
    loop.exec()
    app.processEvents()

    assert len(errors) == 1
    rendered = str(errors[0])
    assert rendered.endswith("TAIL")
    assert len(rendered) < 2200
