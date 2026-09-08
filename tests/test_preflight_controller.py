from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt

from controllers.agent_controller import AgentController
from controllers.preflight_controller import PreflightController
from core.agent.runtime import PiLaunchSpec
from core.preflight import CommandProbe, CommandProbeResult, HostRuntimeFacts, PreflightStatus
from core.settings import AgentSettings, AppSettings, SettingsStore
from ui.models.preflight_model import PreflightListModel


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _write_models(workspace: Path) -> None:
    agent_dir = workspace / ".pi-agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "models.json").write_text(
        json.dumps(
            {
                "providers": {
                    "ornith-lan": {
                        "baseUrl": "http://192.0.2.45:8080/v1",
                        "api": "openai-completions",
                        "apiKey": "pi-ui-local",
                        "models": [{"id": "Ornith", "input": ["text"]}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def _unexpected_transport(
    _spec: PiLaunchSpec,
    _startup_timeout_ms: int,
    _shutdown_timeout_ms: int,
):
    raise AssertionError("preflight tests must not start Pi")


def _agent_controller(tmp_path: Path) -> tuple[AgentController, HostRuntimeFacts]:
    workspace = tmp_path / "AIOS"
    workspace.mkdir()
    _write_models(workspace)
    runtime_root = tmp_path / "runtime"
    pi = _make_executable(runtime_root / "bin" / "pi")
    bwrap = _make_executable(tmp_path / "bin" / "bwrap")
    node = _make_executable(tmp_path / "bin" / "node")
    settings = AppSettings(
        workspace_root=str(workspace),
        agent=AgentSettings(
            executable=str(pi),
            runtime_root=str(runtime_root),
            bubblewrap_executable=str(bwrap),
        ),
    )
    controller = AgentController(
        SettingsStore(tmp_path / "settings.json"),
        _unexpected_transport,
        settings=settings,
    )
    facts = HostRuntimeFacts(
        os_name="Linux",
        os_release="test-kernel",
        python_version="3.13.0",
        pyside_version="6.11.2",
        qt_version="6.11.2",
        node_executable=str(node),
    )
    return controller, facts


class ImmediateRunner:
    def __init__(self) -> None:
        self._running = False

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
        assert dict(environment)["PI_OFFLINE"] == "1"
        self._running = True
        for probe in probes:
            result_handler(
                CommandProbeResult(
                    probe_id=probe.probe_id,
                    exit_code=0,
                    stdout=f"{probe.probe_id} test-version\n",
                    stderr="",
                )
            )
        self._running = False
        finished_handler()

    def cancel(self) -> None:
        self._running = False


class HeldRunner:
    def __init__(self) -> None:
        self._running = False
        self.cancelled = False
        self.result_handler: Callable[[CommandProbeResult], None] | None = None
        self.finished_handler: Callable[[], None] | None = None
        self.probes: tuple[CommandProbe, ...] = ()

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
        del environment
        self._running = True
        self.probes = probes
        self.result_handler = result_handler
        self.finished_handler = finished_handler

    def cancel(self) -> None:
        self.cancelled = True
        self._running = False


def test_preflight_controller_completes_and_keeps_target_gate_pending(tmp_path: Path) -> None:
    agent_controller, facts = _agent_controller(tmp_path)
    controller = PreflightController(agent_controller, ImmediateRunner, facts)
    model = PreflightListModel(controller)

    controller.run()

    assert controller.running is False
    assert controller.fail_count == 0
    assert controller.warning_count == 1
    assert controller.pending_count == 1
    assert controller.status_text == "Host preflight passed · target sandbox gate still pending"
    assert controller.manifest
    assert model.rowCount() == len(controller.checks)

    statuses = {
        model.data(model.index(row, 0), PreflightListModel.StatusRole)
        for row in range(model.rowCount())
    }
    assert "pass" in statuses
    assert "warn" in statuses
    assert "pending" in statuses

    display = model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole)
    assert isinstance(display, str) and display


def test_cancelled_preflight_ignores_late_runner_callbacks(tmp_path: Path) -> None:
    agent_controller, facts = _agent_controller(tmp_path)
    runner = HeldRunner()
    controller = PreflightController(agent_controller, lambda: runner, facts)

    controller.run()
    assert controller.running is True
    assert runner.probes

    controller.cancel()
    assert runner.cancelled is True
    assert controller.running is False
    assert controller.status_text == "Preflight cancelled"
    assert controller.manifest == ""

    assert runner.finished_handler is not None
    runner.finished_handler()
    assert controller.status_text == "Preflight cancelled"
    assert controller.manifest == ""

    assert runner.result_handler is not None
    runner.result_handler(
        CommandProbeResult(
            probe_id=runner.probes[0].probe_id,
            exit_code=0,
            stdout="late success\n",
            stderr="",
        )
    )
    assert controller.status_text == "Preflight cancelled"


def test_second_run_replaces_previous_results(tmp_path: Path) -> None:
    agent_controller, facts = _agent_controller(tmp_path)
    runners: list[Any] = []

    def factory() -> ImmediateRunner:
        runner = ImmediateRunner()
        runners.append(runner)
        return runner

    controller = PreflightController(agent_controller, factory, facts)
    resets: list[int] = []
    controller.set_checks_reset_handler(lambda checks: resets.append(len(checks)))

    controller.run()
    first_manifest = controller.manifest
    controller.run()

    assert len(runners) == 2
    assert len(resets) == 2
    assert controller.manifest == first_manifest
    assert controller.fail_count == 0
    assert any(check.status == PreflightStatus.PENDING for check in controller.checks)
