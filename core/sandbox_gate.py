"""Active M0 Bubblewrap confinement gate using the canonical sandbox policy."""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from uuid import uuid4

from core.agent.runtime import PiRuntimePaths, SANDBOX_WORKSPACE
from core.preflight import CommandProbe, CommandProbeResult, PreflightCheck, PreflightStatus
from core.sandbox import SANDBOX_HOME, build_bubblewrap_arguments, command_is_visible_in_sandbox
from core.settings import AgentSettings

_GATE_TIMEOUT_MS: Final = 10_000
_RUN_ID_RE: Final = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_EXPECTED_CHECKS: Final = (
    ("workspace-root", "Sandbox working directory"),
    ("workspace-write", "AIOS workspace is writable"),
    ("outside-direct", "Outside sentinel is unreadable"),
    ("symlink-escape", "Symlink cannot escape workspace"),
    ("child-inherits", "Child process inherits confinement"),
    ("runtime-readonly", "Managed Pi runtime is read-only"),
    ("usr-readonly", "/usr is read-only"),
    ("synthetic-home", "HOME is synthetic"),
    ("desktop-env", "Desktop/session environment is absent"),
    ("runtime-sockets", "Host runtime sockets are not mounted"),
    ("pid-namespace", "Host PID is hidden"),
)

_GATE_SCRIPT: Final = r'''import fs from "node:fs";
import { spawnSync } from "node:child_process";

const [outsidePath, symlinkPath, runtimeRoot, expectedHome, hostPid] = process.argv.slice(2);
const scratch = "/workspace/.pi-agent/__RUN_DIR__";
const checks = [];

function add(id, passed, detail = "") {
  checks.push({ id, passed: Boolean(passed), detail: String(detail || "") });
}

function readDenied(path) {
  try {
    fs.readFileSync(path);
    return [false, "read unexpectedly succeeded"];
  } catch (error) {
    return [true, error?.code || error?.name || "read denied"];
  }
}

function writeDenied(path) {
  try {
    fs.writeFileSync(path, "pi-ui-gate", { flag: "wx" });
    try { fs.unlinkSync(path); } catch {}
    return [false, "write unexpectedly succeeded"];
  } catch (error) {
    return [true, error?.code || error?.name || "write denied"];
  }
}

add("workspace-root", process.cwd() === "/workspace", process.cwd());

const insideWrite = `${scratch}/inside-write.txt`;
try {
  fs.writeFileSync(insideWrite, "workspace-ok", { flag: "wx" });
  const roundTrip = fs.readFileSync(insideWrite, "utf8") === "workspace-ok";
  fs.unlinkSync(insideWrite);
  add("workspace-write", roundTrip, roundTrip ? "round-trip ok" : "round-trip mismatch");
} catch (error) {
  add("workspace-write", false, error?.code || error?.message || "workspace write failed");
}

{
  const [passed, detail] = readDenied(outsidePath);
  add("outside-direct", passed, detail);
}
{
  const [passed, detail] = readDenied(symlinkPath);
  add("symlink-escape", passed, detail);
}
{
  const childCode = "const fs=require('fs');fs.readFileSync(process.argv[1])";
  const child = spawnSync(process.execPath, ["-e", childCode, symlinkPath], { stdio: "ignore" });
  add("child-inherits", child.status !== 0, `exit=${child.status}`);
}
{
  const [passed, detail] = writeDenied(`${runtimeRoot}/.pi-ui-gate-write`);
  add("runtime-readonly", passed, detail);
}
{
  const [passed, detail] = writeDenied("/usr/.pi-ui-gate-write");
  add("usr-readonly", passed, detail);
}

add(
  "synthetic-home",
  process.env.HOME === expectedHome && fs.existsSync(expectedHome),
  process.env.HOME || "HOME unset",
);

const forbiddenEnv = [
  "DISPLAY",
  "WAYLAND_DISPLAY",
  "DBUS_SESSION_BUS_ADDRESS",
  "SSH_AUTH_SOCK",
  "GPG_AGENT_INFO",
  "XDG_RUNTIME_DIR",
];
const exposed = forbiddenEnv.filter((key) => process.env[key]);
add("desktop-env", exposed.length === 0, exposed.length ? exposed.join(",") : "none exposed");
add("runtime-sockets", !fs.existsSync("/run/user"), fs.existsSync("/run/user") ? "/run/user visible" : "hidden");
add("pid-namespace", !fs.existsSync(`/proc/${hostPid}`), `hostPid=${hostPid}`);

const passed = checks.every((item) => item.passed);
process.stdout.write(JSON.stringify({ schema: 1, passed, checks }) + "\n");
process.exit(passed ? 0 : 2);
'''


class SandboxGateError(RuntimeError):
    """Raised when the active gate cannot be prepared or interpreted safely."""


@dataclass(frozen=True, slots=True)
class SandboxGatePlan:
    run_id: str
    probe: CommandProbe
    environment: tuple[tuple[str, str], ...]
    scratch_dir: Path
    outside_run_dir: Path
    outside_sentinel: Path
    agent_dir_created: bool


@dataclass(frozen=True, slots=True)
class SandboxGateReport:
    checks: tuple[PreflightCheck, ...]
    process_exit_code: int | None
    timed_out: bool
    start_error: str | None

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(
            check.status == PreflightStatus.PASS for check in self.checks
        )


class SandboxGateService:
    """Prepare, parse and clean up one explicit active confinement gate."""

    def __init__(self, id_factory: Callable[[], str] | None = None) -> None:
        self._id_factory = id_factory or (lambda: uuid4().hex)

    def prepare(
        self,
        settings: AgentSettings,
        *,
        workspace: Path,
        node_executable: str,
        outside_root: Path,
        base_environment: Mapping[str, str] | None = None,
        host_pid: int | None = None,
    ) -> SandboxGatePlan:
        if not settings.sandbox_enabled:
            raise SandboxGateError("active confinement gate requires Bubblewrap sandboxing")

        workspace = workspace.expanduser().resolve()
        if not workspace.is_dir():
            raise SandboxGateError(f"workspace is unavailable: {workspace}")
        if not command_is_visible_in_sandbox(
            node_executable,
            runtime_root=settings.runtime_root,
        ):
            raise SandboxGateError(
                "Node executable is not visible inside the canonical sandbox mounts"
            )
        node_path = Path(node_executable)
        if not node_path.is_file() or not os.access(node_path, os.X_OK):
            raise SandboxGateError(f"Node executable is unavailable: {node_path}")

        outside_base = outside_root.expanduser().resolve()
        self._validate_outside_root(
            outside_base,
            workspace=workspace,
            runtime_root=Path(settings.runtime_root).expanduser().resolve(),
        )

        run_id = self._validated_run_id(self._id_factory())
        paths = PiRuntimePaths.for_workspace(workspace)
        agent_dir_created = not paths.host_agent_dir.exists()
        paths.host_agent_dir.mkdir(mode=0o700, exist_ok=True)
        scratch_dir = paths.host_agent_dir / f".m0-gate-{run_id}"
        outside_run_dir = outside_base / f"m0-gate-{run_id}"
        outside_sentinel = outside_run_dir / "outside-sentinel.txt"

        try:
            scratch_dir.mkdir(mode=0o700)
            outside_run_dir.mkdir(mode=0o700, parents=True)
            outside_sentinel.write_text("pi-ui-outside-sentinel\n", encoding="utf-8")
            script_path = scratch_dir / "probe.mjs"
            script_path.write_text(
                _GATE_SCRIPT.replace("__RUN_DIR__", scratch_dir.name),
                encoding="utf-8",
            )
            symlink_path = scratch_dir / "escape-link"
            symlink_path.symlink_to(outside_sentinel)

            base_env = dict(os.environ if base_environment is None else base_environment)
            sandbox_script = SANDBOX_WORKSPACE / script_path.relative_to(workspace)
            sandbox_symlink = SANDBOX_WORKSPACE / symlink_path.relative_to(workspace)
            sandbox_arguments = build_bubblewrap_arguments(
                settings,
                host_workspace=workspace,
                sandbox_workspace=paths.sandbox_workspace,
                command=(
                    node_executable,
                    str(sandbox_script),
                    str(outside_sentinel),
                    str(sandbox_symlink),
                    settings.runtime_root,
                    str(SANDBOX_HOME),
                    str(host_pid if host_pid is not None else os.getpid()),
                ),
            )
            environment = (
                ("HOME", str(SANDBOX_HOME)),
                ("LANG", base_env.get("LANG", "C.UTF-8")),
                ("PATH", f"{settings.runtime_root}/bin:/usr/bin:/bin"),
                ("PI_OFFLINE", "1"),
                ("PI_SKIP_VERSION_CHECK", "1"),
            )
            probe = CommandProbe(
                probe_id="sandbox-confinement",
                label="Bubblewrap active confinement",
                executable=settings.bubblewrap_executable,
                arguments=sandbox_arguments,
                timeout_ms=_GATE_TIMEOUT_MS,
                required=True,
            )
            return SandboxGatePlan(
                run_id=run_id,
                probe=probe,
                environment=environment,
                scratch_dir=scratch_dir,
                outside_run_dir=outside_run_dir,
                outside_sentinel=outside_sentinel,
                agent_dir_created=agent_dir_created,
            )
        except BaseException:
            self._cleanup_paths(
                scratch_dir,
                outside_run_dir,
                paths.host_agent_dir if agent_dir_created else None,
            )
            raise

    def parse_result(
        self,
        plan: SandboxGatePlan,
        result: CommandProbeResult,
    ) -> SandboxGateReport:
        if result.probe_id != plan.probe.probe_id:
            raise SandboxGateError("sandbox gate result does not match the active probe")
        if result.start_error:
            return self._process_failure(result, "Bubblewrap gate could not start")
        if result.timed_out:
            return self._process_failure(
                result,
                f"Bubblewrap gate exceeded {plan.probe.timeout_ms} ms",
            )

        payload = self._parse_payload(result.stdout)
        raw_checks = payload.get("checks")
        if payload.get("schema") != 1 or not isinstance(raw_checks, list):
            return self._process_failure(result, "Sandbox gate returned an invalid payload")

        expected = {check_id: label for check_id, label in _EXPECTED_CHECKS}
        parsed: dict[str, PreflightCheck] = {}
        for item in raw_checks:
            if not isinstance(item, dict):
                return self._process_failure(result, "Sandbox gate returned an invalid check")
            check_id = item.get("id")
            passed = item.get("passed")
            detail = item.get("detail", "")
            if (
                not isinstance(check_id, str)
                or check_id not in expected
                or check_id in parsed
                or not isinstance(passed, bool)
                or not isinstance(detail, str)
            ):
                return self._process_failure(result, "Sandbox gate returned ambiguous checks")
            parsed[check_id] = PreflightCheck(
                check_id=f"sandbox-{check_id}",
                label=expected[check_id],
                status=PreflightStatus.PASS if passed else PreflightStatus.FAIL,
                summary="Confinement verified" if passed else "Confinement check failed",
                detail=_limit_detail(detail),
            )

        if set(parsed) != set(expected):
            return self._process_failure(result, "Sandbox gate omitted required checks")

        checks = tuple(parsed[check_id] for check_id, _label in _EXPECTED_CHECKS)
        if result.exit_code not in {0, 2}:
            checks += (
                PreflightCheck(
                    "sandbox-process-exit",
                    "Sandbox probe process",
                    PreflightStatus.FAIL,
                    f"Unexpected process exit code {result.exit_code}",
                    _first_line(result.stderr),
                ),
            )
        elif result.exit_code == 0 and any(
            check.status != PreflightStatus.PASS for check in checks
        ):
            checks += (
                PreflightCheck(
                    "sandbox-process-consistency",
                    "Sandbox probe consistency",
                    PreflightStatus.FAIL,
                    "Probe claimed success while one or more checks failed",
                ),
            )
        elif result.exit_code == 2 and all(
            check.status == PreflightStatus.PASS for check in checks
        ):
            checks += (
                PreflightCheck(
                    "sandbox-process-consistency",
                    "Sandbox probe consistency",
                    PreflightStatus.FAIL,
                    "Probe exited as failed while all checks claimed success",
                ),
            )

        return SandboxGateReport(
            checks=checks,
            process_exit_code=result.exit_code,
            timed_out=False,
            start_error=None,
        )

    def cleanup(self, plan: SandboxGatePlan) -> None:
        agent_dir = plan.scratch_dir.parent if plan.agent_dir_created else None
        self._cleanup_paths(plan.scratch_dir, plan.outside_run_dir, agent_dir)

    @staticmethod
    def sanitized_manifest_json(report: SandboxGateReport) -> str:
        payload = {
            "schema": 1,
            "passed": report.passed,
            "processExitCode": report.process_exit_code,
            "timedOut": report.timed_out,
            "startError": bool(report.start_error),
            "checks": [
                {
                    "id": check.check_id,
                    "label": check.label,
                    "status": str(check.status),
                    "summary": check.summary,
                    "detail": "",
                }
                for check in report.checks
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    @staticmethod
    def _parse_payload(stdout: str) -> dict[str, object]:
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        if len(lines) != 1:
            return {}
        try:
            payload = json.loads(lines[0])
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _process_failure(
        result: CommandProbeResult,
        summary: str,
    ) -> SandboxGateReport:
        detail = result.start_error or _first_line(result.stderr) or _first_line(result.stdout)
        return SandboxGateReport(
            checks=(
                PreflightCheck(
                    "sandbox-gate-process",
                    "Bubblewrap active confinement",
                    PreflightStatus.FAIL,
                    summary,
                    _limit_detail(detail),
                ),
            ),
            process_exit_code=result.exit_code,
            timed_out=result.timed_out,
            start_error=result.start_error,
        )

    @staticmethod
    def _validated_run_id(value: str) -> str:
        if not isinstance(value, str) or not _RUN_ID_RE.fullmatch(value):
            raise SandboxGateError("gate id must be a short filesystem-safe token")
        return value

    @staticmethod
    def _validate_outside_root(
        outside_root: Path,
        *,
        workspace: Path,
        runtime_root: Path,
    ) -> None:
        for mounted_root, label in (
            (workspace, "workspace"),
            (runtime_root, "runtime_root"),
            (Path("/usr"), "/usr"),
        ):
            try:
                outside_root.relative_to(mounted_root)
            except ValueError:
                continue
            raise SandboxGateError(
                f"outside sentinel root must not be inside mounted {label}"
            )

    @staticmethod
    def _cleanup_paths(
        scratch_dir: Path,
        outside_run_dir: Path,
        agent_dir_if_created: Path | None,
    ) -> None:
        shutil.rmtree(scratch_dir, ignore_errors=True)
        shutil.rmtree(outside_run_dir, ignore_errors=True)
        if agent_dir_if_created is not None:
            try:
                agent_dir_if_created.rmdir()
            except OSError:
                pass


def _limit_detail(value: str) -> str:
    return value[:500]


def _first_line(value: str) -> str:
    for line in value.splitlines():
        line = line.strip()
        if line:
            return _limit_detail(line)
    return ""
