from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from controllers.agent_controller import AgentController
from controllers.sandbox_gate_controller import SandboxGateController
from core.agent.runtime import PiLaunchSpec
from core.preflight import CommandProbe, CommandProbeResult, HostRuntimeFacts, PreflightStatus
from core.settings import AgentSettings, AppSettings, SettingsStore

_CHECK_IDS = (
    "workspace-root",
    "workspace-write",
    "outside-direct",
    "symlink-escape",
    "child-inherits",
    "runtime-readonly",
    "usr-readonly",
    "synthetic-home",
    "desktop-env",
    "runtime-sockets",
    "pid-namespace",
)


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _unexpected_transport(
    _spec: PiLaunchSpec,
    _startup_timeout_ms: int,
    _shutdown_timeout_ms: int,
):
    raise AssertionError("sandbox gate controller test must not start Pi")


def _fixture(tmp_path: Path):
    workspace = tmp_path / "AIOS"
    workspace.mkdir()
    runtime_root = tmp_path / "runtime"
    pi = _make_executable(runtime_root / "bin" / "pi")
    node = _make_executable(runtime_root / "bin" / "node")
    bwrap = _make_executable(tmp_path / "bin" / "bwrap")
    settings = AppSettings(
        workspace_root=str(workspace),
        agent=AgentSettings(
            executable=str(pi),
            runtime_root=str(runtime_root),
            bubblewrap_executable=str(bwrap),
        ),
    )
    agent = AgentController(
        SettingsStore(tmp_path / "settings.json"),
        _unexpected_transport,
        settings=settings,
    )
    facts = HostRuntimeFacts(
        os_name="Linux",
        os_release="test",
        python_version="3.13",
        pyside_version="6.11.2",
        qt_version="6.11.2",
        node_executable=str(node),
    )
    return agent, facts


class HeldRunner:
    def __init__(self) -> None:
        self._running = False
        self.probe: CommandProbe | None = None
        self.result_handler: Callable[[CommandProbeResult], None] | None = None
        self.finished_handler: Callable[[], None] | None = None
        self.cancelled = False

    @property
    def running(self) -> bool:
        return self._running

    def start(
        self,
        probes: tuple[CommandProbe, ...],
        *,
        environment: tuple[tuple[str, str], ...],
        result_handler: Callable[[CommandProbeResult], None],
        finished_handler: Callable[[], None],
    ) -> None:
        assert len(probes) == 1
        assert dict(environment)["PI_OFFLINE"] == "1"
        self._running = True
        self.probe = probes[0]
        self.result_handler = result_handler
        self.finished_handler = finished_handler

    def cancel(self) -> None:
        self.cancelled = True
        self._running = False


def _success_result() -> CommandProbeResult:
    payload = {
        "schema": 1,
        "passed": True,
        "checks": [
            {"id": check_id, "passed": True, "detail": "verified"}
            for check_id in _CHECK_IDS
        ],
    }
    return CommandProbeResult(
        probe_id="sandbox-confinement",
        exit_code=0,
        stdout=json.dumps(payload) + "\n",
        stderr="",
    )


def test_controller_runs_explicit_gate_and_cleans_fixtures(tmp_path: Path) -> None:
    agent, facts = _fixture(tmp_path)
    runner = HeldRunner()
    controller = SandboxGateController(
        agent,
        lambda: runner,
        facts,
        outside_root=tmp_path / "outside",
    )

    assert controller.can_run is True
    controller.run()
    assert controller.running is True
    assert runner.probe is not None
    assert list((agent.workspace / ".pi-agent").glob(".m0-gate-*"))

    assert runner.result_handler is not None
    runner.result_handler(_success_result())

    assert controller.running is False
    assert controller.fail_count == 0
    assert controller.pass_count == len(_CHECK_IDS)
    assert controller.status_text.startswith("Sandbox confinement passed")
    assert controller.manifest
    assert all(check.status == PreflightStatus.PASS for check in controller.checks)
    assert not list((agent.workspace / ".pi-agent").glob(".m0-gate-*"))
    assert not list((tmp_path / "outside").glob("m0-gate-*"))


def test_cancel_removes_fixtures_and_ignores_late_callbacks(tmp_path: Path) -> None:
    agent, facts = _fixture(tmp_path)
    runner = HeldRunner()
    controller = SandboxGateController(
        agent,
        lambda: runner,
        facts,
        outside_root=tmp_path / "outside",
    )

    controller.run()
    result_handler = runner.result_handler
    finished_handler = runner.finished_handler
    controller.cancel()

    assert runner.cancelled is True
    assert controller.running is False
    assert controller.status_text == "Sandbox gate cancelled"
    assert controller.manifest == ""
    assert not list((agent.workspace / ".pi-agent").glob(".m0-gate-*"))
    assert not list((tmp_path / "outside").glob("m0-gate-*"))

    assert result_handler is not None and finished_handler is not None
    result_handler(_success_result())
    finished_handler()
    assert controller.status_text == "Sandbox gate cancelled"
    assert controller.manifest == ""


def test_can_run_rejects_node_that_host_can_execute_but_sandbox_cannot_see(
    tmp_path: Path,
) -> None:
    agent, facts = _fixture(tmp_path)
    host_only_node = _make_executable(tmp_path / "home" / "tester" / ".local" / "bin" / "node")
    facts = HostRuntimeFacts(
        os_name=facts.os_name,
        os_release=facts.os_release,
        python_version=facts.python_version,
        pyside_version=facts.pyside_version,
        qt_version=facts.qt_version,
        node_executable=str(host_only_node),
    )
    controller = SandboxGateController(
        agent,
        HeldRunner,
        facts,
        outside_root=tmp_path / "outside",
    )

    assert controller.can_run is False
