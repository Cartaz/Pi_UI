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


def test_qprocess_transport_keeps_stdout_protocol_separate_from_stderr(
    tmp_path: Path,
) -> None:
    _application()
    script = tmp_path / "fake_pi.py"
    script.write_text(
        """
import json
import sys

print("diagnostic: booted", file=sys.stderr, flush=True)
for line in sys.stdin:
    command = json.loads(line)
    print(json.dumps({
        "id": command.get("id"),
        "type": "response",
        "command": command["type"],
        "success": True,
    }), flush=True)
""".lstrip(),
        encoding="utf-8",
    )

    paths = PiRuntimePaths.for_workspace(tmp_path)
    spec = PiLaunchSpec(
        executable=sys.executable,
        arguments=("-u", str(script)),
        environment={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        working_directory=tmp_path,
        paths=paths,
    )
    transport = QProcessAgentTransport(
        spec,
        startup_timeout_ms=2_000,
        shutdown_timeout_ms=500,
    )

    states: list[TransportState] = []
    records: list[dict[str, object]] = []
    diagnostics: list[str] = []
    errors: list[BaseException] = []
    loop = QEventLoop()
    timed_out = False

    def on_state(state: TransportState) -> None:
        states.append(state)
        if state is TransportState.READY:
            transport.send({"id": "req-1", "type": "get_state"})
        elif state in {TransportState.STOPPED, TransportState.FAILED}:
            loop.quit()

    def on_record(record: dict[str, object]) -> None:
        records.append(record)
        transport.stop()

    def timeout() -> None:
        nonlocal timed_out
        timed_out = True
        transport.stop()
        loop.quit()

    transport.set_state_handler(on_state)
    transport.set_record_handler(on_record)
    transport.set_diagnostic_handler(diagnostics.append)
    transport.set_error_handler(errors.append)

    QTimer.singleShot(5_000, timeout)
    transport.start()
    loop.exec()

    assert not timed_out
    assert not errors
    assert records == [
        {
            "id": "req-1",
            "type": "response",
            "command": "get_state",
            "success": True,
        }
    ]
    assert "diagnostic: booted" in "".join(diagnostics)
    assert states[0] is TransportState.STARTING
    assert TransportState.READY in states
    assert TransportState.STOPPING in states
    assert states[-1] is TransportState.STOPPED
