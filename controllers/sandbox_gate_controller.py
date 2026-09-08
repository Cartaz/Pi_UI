"""Controller for the explicit M0 Bubblewrap active confinement gate."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from controllers.agent_controller import AgentController, ConnectionState
from core.preflight import CommandProbe, CommandProbeResult, HostRuntimeFacts, PreflightCheck, PreflightStatus
from core.sandbox_gate import SandboxGatePlan, SandboxGateService
from core.settings import default_state_dir

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


class SandboxGateControllerError(RuntimeError):
    """Raised when the active sandbox gate cannot run safely."""


class SandboxGateController:
    """Own one temporary active Bubblewrap verification run."""

    def __init__(
        self,
        agent_controller: AgentController,
        runner_factory: ProbeRunnerFactory,
        facts: HostRuntimeFacts,
        *,
        service: SandboxGateService | None = None,
        outside_root: Path | None = None,
    ) -> None:
        self._agent_controller = agent_controller
        self._runner_factory = runner_factory
        self._facts = facts
        self._service = service or SandboxGateService()
        self._outside_root = outside_root or (default_state_dir() / "sandbox-gates")
        self._runner: ProbeRunner | None = None
        self._plan: SandboxGatePlan | None = None
        self._generation = 0
        self._running = False
        self._checks: list[PreflightCheck] = []
        self._status_text = "Sandbox gate not run"
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
        return sum(check.status == PreflightStatus.FAIL for check in self._checks)

    @property
    def pass_count(self) -> int:
        return sum(check.status == PreflightStatus.PASS for check in self._checks)

    @property
    def can_run(self) -> bool:
        settings = self._agent_controller.settings.agent
        return (
            not self._running
            and self._agent_controller.workspace is not None
            and self._agent_controller.connection_state
            in {ConnectionState.DISCONNECTED, ConnectionState.FAILED}
            and settings.sandbox_enabled
            and self._facts.os_name == "Linux"
            and self._facts.node_executable is not None
        )

    def set_state_handler(self, handler: StateHandler) -> None:
        self._state_handler = handler

    def set_checks_reset_handler(self, handler: ChecksResetHandler) -> None:
        self._checks_reset_handler = handler

    def set_check_changed_handler(self, handler: CheckChangedHandler) -> None:
        self._check_changed_handler = handler

    def run(self) -> None:
        if not self.can_run:
            raise SandboxGateControllerError(
                "sandbox gate requires Linux, a workspace, visible Node and disconnected Pi"
            )
        workspace = self._agent_controller.workspace
        node_executable = self._facts.node_executable
        assert workspace is not None and node_executable is not None

        self._generation += 1
        run_id = self._generation
        self._manifest = ""
        self._checks = [
            PreflightCheck(
                "sandbox-active",
                "Bubblewrap active confinement",
                PreflightStatus.PENDING,
                "Preparing controlled sandbox probe",
                "Temporary scratch data will be removed after the run.",
            )
        ]
        self._checks_reset_handler(tuple(self._checks))
        self._status_text = "Preparing active sandbox gate"
        self._state_handler()

        plan: SandboxGatePlan | None = None
        try:
            plan = self._service.prepare(
                self._agent_controller.settings.agent,
                workspace=workspace,
                node_executable=node_executable,
                outside_root=self._outside_root,
            )
            runner = self._runner_factory()
            self._plan = plan
            self._runner = runner
            self._running = True
            self._status_text = "Running Bubblewrap confinement checks"
            self._state_handler()
            runner.start(
                (plan.probe,),
                environment=plan.environment,
                result_handler=lambda result: self._on_result(result, run_id),
                finished_handler=lambda: self._on_runner_finished(run_id),
            )
        except BaseException as exc:
            if plan is not None:
                self._service.cleanup(plan)
            self._plan = None
            self._runner = None
            self._running = False
            self._status_text = f"Sandbox gate could not start: {exc}"
            self._checks = [
                PreflightCheck(
                    "sandbox-gate-start",
                    "Bubblewrap active confinement",
                    PreflightStatus.FAIL,
                    "Gate could not start",
                    str(exc)[:500],
                )
            ]
            self._checks_reset_handler(tuple(self._checks))
            self._state_handler()
            raise

    def cancel(self) -> None:
        self._generation += 1
        runner = self._runner
        plan = self._plan
        self._runner = None
        self._plan = None
        self._running = False
        if runner is not None:
            runner.cancel()
        if plan is not None:
            self._service.cleanup(plan)
        self._manifest = ""
        self._status_text = "Sandbox gate cancelled"
        self._state_handler()

    def _on_result(self, result: CommandProbeResult, run_id: int) -> None:
        if run_id != self._generation:
            return
        plan = self._plan
        if plan is None:
            return
        try:
            report = self._service.parse_result(plan, result)
            self._checks = list(report.checks)
            self._manifest = self._service.sanitized_manifest_json(report)
            self._status_text = (
                f"Sandbox confinement passed · {len(report.checks)} checks"
                if report.passed
                else f"Sandbox confinement failed · {self.fail_count} issue(s)"
            )
        finally:
            self._service.cleanup(plan)
            self._plan = None
            self._runner = None
            self._running = False
            self._generation += 1
        self._checks_reset_handler(tuple(self._checks))
        self._state_handler()

    def _on_runner_finished(self, run_id: int) -> None:
        if run_id != self._generation:
            return
        plan = self._plan
        if plan is None:
            return
        self._on_result(
            CommandProbeResult(
                probe_id=plan.probe.probe_id,
                exit_code=None,
                stdout="",
                stderr="",
                start_error="probe runner finished without a result",
            ),
            run_id,
        )
