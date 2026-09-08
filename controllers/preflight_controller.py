"""Presentation-independent controller for the M0 host preflight."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from controllers.agent_controller import AgentController
from core.agent import PiModelsConfigDiscovery, PiRuntimePaths
from core.preflight import (
    CommandProbe,
    CommandProbeResult,
    HostRuntimeFacts,
    PreflightCheck,
    PreflightPlanner,
    PreflightStatus,
    classify_probe_result,
    sanitized_manifest_json,
)

StateHandler = Callable[[], None]
ChecksResetHandler = Callable[[tuple[PreflightCheck, ...]], None]
CheckChangedHandler = Callable[[int, PreflightCheck], None]


class ProbeRunner(Protocol):
    @property
    def running(self) -> bool: ...

    def start(
        self,
        probes: tuple[CommandProbe, ...],
        *,
        environment: tuple[tuple[str, str], ...],
        result_handler: Callable[[CommandProbeResult], None],
        finished_handler: Callable[[], None],
    ) -> None: ...

    def cancel(self) -> None: ...


ProbeRunnerFactory = Callable[[], ProbeRunner]


class PreflightControllerError(RuntimeError):
    """Raised when preflight cannot start in the current state."""


class PreflightController:
    """Own one read-only preflight run and its presentation-ready results."""

    def __init__(
        self,
        agent_controller: AgentController,
        runner_factory: ProbeRunnerFactory,
        facts: HostRuntimeFacts,
        *,
        planner: PreflightPlanner | None = None,
        discovery: PiModelsConfigDiscovery | None = None,
    ) -> None:
        self._agent_controller = agent_controller
        self._runner_factory = runner_factory
        self._facts = facts
        self._planner = planner or PreflightPlanner()
        self._discovery = discovery or PiModelsConfigDiscovery()
        self._runner: ProbeRunner | None = None
        self._checks: list[PreflightCheck] = []
        self._probe_indices: dict[str, int] = {}
        self._running = False
        self._generation = 0
        self._status_text = "Preflight not run"
        self._manifest = ""
        self._state_handler: StateHandler = lambda: None
        self._checks_reset_handler: ChecksResetHandler = lambda _checks: None
        self._check_changed_handler: CheckChangedHandler = lambda _index, _check: None

    @property
    def checks(self) -> tuple[PreflightCheck, ...]:
        return tuple(self._checks)

    @property
    def running(self) -> bool:
        return self._running

    @property
    def status_text(self) -> str:
        return self._status_text

    @property
    def manifest(self) -> str:
        return self._manifest

    @property
    def fail_count(self) -> int:
        return sum(item.status == PreflightStatus.FAIL for item in self._checks)

    @property
    def warning_count(self) -> int:
        return sum(item.status == PreflightStatus.WARN for item in self._checks)

    @property
    def pending_count(self) -> int:
        return sum(item.status == PreflightStatus.PENDING for item in self._checks)

    def set_state_handler(self, handler: StateHandler) -> None:
        self._state_handler = handler

    def set_checks_reset_handler(self, handler: ChecksResetHandler) -> None:
        self._checks_reset_handler = handler

    def set_check_changed_handler(self, handler: CheckChangedHandler) -> None:
        self._check_changed_handler = handler

    def run(self) -> None:
        if self._running:
            raise PreflightControllerError("preflight is already running")

        self._generation += 1
        run_id = self._generation
        workspace = self._agent_controller.workspace
        existing = None
        if workspace is not None:
            existing = self._discovery.inspect(PiRuntimePaths.for_workspace(workspace))

        plan = self._planner.build(
            self._agent_controller.settings.agent,
            workspace=workspace,
            existing_models=existing,
            facts=self._facts,
        )
        self._checks = list(plan.checks)
        self._probe_indices = {
            check.check_id: index for index, check in enumerate(self._checks)
        }
        self._manifest = ""
        self._checks_reset_handler(tuple(self._checks))

        if not plan.probes:
            self._finish(run_id)
            return

        self._running = True
        self._status_text = "Running host preflight"
        self._state_handler()
        runner = self._runner_factory()
        self._runner = runner
        try:
            runner.start(
                plan.probes,
                environment=plan.environment,
                result_handler=lambda result: self._on_probe_result(
                    plan.probes,
                    result,
                    run_id,
                ),
                finished_handler=lambda: self._finish(run_id),
            )
        except BaseException as exc:
            self._generation += 1
            self._runner = None
            self._running = False
            self._status_text = f"Preflight runner failed to start: {exc}"
            self._state_handler()
            raise

    def cancel(self) -> None:
        self._generation += 1
        runner = self._runner
        if runner is not None:
            runner.cancel()
        self._runner = None
        self._running = False
        self._status_text = "Preflight cancelled"
        self._state_handler()

    def _on_probe_result(
        self,
        probes: tuple[CommandProbe, ...],
        result: CommandProbeResult,
        run_id: int,
    ) -> None:
        if run_id != self._generation:
            return
        probe = next((item for item in probes if item.probe_id == result.probe_id), None)
        if probe is None:
            return
        index = self._probe_indices.get(result.probe_id)
        if index is None:
            return
        check = classify_probe_result(probe, result)
        self._checks[index] = check
        self._check_changed_handler(index, check)
        self._state_handler()

    def _finish(self, run_id: int) -> None:
        if run_id != self._generation:
            return
        self._runner = None
        self._running = False
        self._manifest = sanitized_manifest_json(tuple(self._checks), self._facts)
        if self.fail_count:
            self._status_text = f"Preflight found {self.fail_count} blocking issue(s)"
        elif self.pending_count:
            self._status_text = "Host preflight passed · target sandbox gate still pending"
        elif self.warning_count:
            self._status_text = "Host preflight passed with warnings"
        else:
            self._status_text = "Host preflight passed"
        self._state_handler()
