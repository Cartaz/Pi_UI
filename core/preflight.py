"""Pure preflight planning and result classification for the M0 local gate."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from core.agent.model_discovery import ExistingModelsConfig, ModelConfigManagementState
from core.sandbox import command_is_visible_in_sandbox
from core.settings import AgentSettings

_MAX_PROBE_TEXT: Final = 1000


class PreflightStatus(StrEnum):
    PENDING = "pending"
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class HostRuntimeFacts:
    os_name: str
    os_release: str
    python_version: str
    pyside_version: str
    qt_version: str
    node_executable: str | None


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    check_id: str
    label: str
    status: PreflightStatus
    summary: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class CommandProbe:
    probe_id: str
    label: str
    executable: str
    arguments: tuple[str, ...]
    timeout_ms: int = 5_000
    required: bool = True


@dataclass(frozen=True, slots=True)
class CommandProbeResult:
    probe_id: str
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    start_error: str | None = None


@dataclass(frozen=True, slots=True)
class PreflightPlan:
    checks: tuple[PreflightCheck, ...]
    probes: tuple[CommandProbe, ...]
    environment: tuple[tuple[str, str], ...]


class PreflightPlanner:
    """Build a read-only host/runtime preflight from canonical settings."""

    def build(
        self,
        settings: AgentSettings,
        *,
        workspace: Path | None,
        existing_models: ExistingModelsConfig | None,
        facts: HostRuntimeFacts,
    ) -> PreflightPlan:
        checks: list[PreflightCheck] = []
        probes: list[CommandProbe] = []

        checks.append(
            PreflightCheck(
                "host-os",
                "Host operating system",
                PreflightStatus.PASS if facts.os_name == "Linux" else PreflightStatus.FAIL,
                f"{facts.os_name} {facts.os_release}".strip(),
                "Bubblewrap confinement is an M0 Linux requirement.",
            )
        )
        checks.append(
            PreflightCheck(
                "python",
                "Python / Qt runtime",
                PreflightStatus.PASS,
                f"Python {facts.python_version} · PySide6 {facts.pyside_version} · Qt {facts.qt_version}",
            )
        )

        if workspace is None:
            checks.append(
                PreflightCheck(
                    "workspace",
                    "AIOS workspace",
                    PreflightStatus.FAIL,
                    "No workspace selected",
                )
            )
        else:
            resolved = workspace.expanduser().resolve()
            checks.append(
                PreflightCheck(
                    "workspace",
                    "AIOS workspace",
                    PreflightStatus.PASS if resolved.is_dir() else PreflightStatus.FAIL,
                    "Workspace directory is available" if resolved.is_dir() else "Workspace directory is unavailable",
                    str(resolved),
                )
            )

        checks.append(
            PreflightCheck(
                "sandbox-enabled",
                "Bubblewrap policy",
                PreflightStatus.PASS if settings.sandbox_enabled else PreflightStatus.FAIL,
                "Sandbox required" if settings.sandbox_enabled else "Sandbox is disabled",
                "Pi_UI does not silently fall back to an unsandboxed Pi process.",
            )
        )

        self._add_executable_check(
            checks,
            probes,
            check_id="bubblewrap",
            label="Bubblewrap runtime",
            executable=settings.bubblewrap_executable,
            arguments=("--version",),
            required=settings.sandbox_enabled,
        )
        self._add_executable_check(
            checks,
            probes,
            check_id="pi",
            label="Pi Agent runtime",
            executable=settings.executable,
            arguments=("--version",),
            required=True,
        )

        runtime_root = Path(settings.runtime_root)
        runtime_ok = runtime_root.is_dir()
        checks.append(
            PreflightCheck(
                "runtime-root",
                "Managed Pi runtime root",
                PreflightStatus.PASS if runtime_ok else PreflightStatus.FAIL,
                "Runtime root is available" if runtime_ok else "Runtime root is missing",
                str(runtime_root),
            )
        )

        if facts.node_executable:
            node_path = Path(facts.node_executable)
            node_ok = node_path.is_file() and os.access(node_path, os.X_OK)
            sandbox_visible = (
                not settings.sandbox_enabled
                or command_is_visible_in_sandbox(
                    str(node_path),
                    runtime_root=settings.runtime_root,
                )
            )
            if node_ok and sandbox_visible:
                checks.append(
                    PreflightCheck(
                        "node",
                        "Node.js runtime",
                        PreflightStatus.PENDING,
                        "Version probe pending",
                        str(node_path),
                    )
                )
                probes.append(
                    CommandProbe(
                        probe_id="node",
                        label="Node.js runtime",
                        executable=str(node_path),
                        arguments=("--version",),
                    )
                )
            else:
                summary = (
                    "Node executable is unavailable"
                    if not node_ok
                    else "Node exists on the host but is not mounted into the sandbox"
                )
                checks.append(
                    PreflightCheck(
                        "node",
                        "Node.js runtime",
                        PreflightStatus.FAIL,
                        summary,
                        str(node_path),
                    )
                )
        else:
            checks.append(
                PreflightCheck(
                    "node",
                    "Node.js runtime",
                    PreflightStatus.FAIL,
                    "Node executable was not found on PATH",
                )
            )

        checks.append(self._models_check(existing_models))
        checks.append(
            PreflightCheck(
                "network-policy",
                "Sandbox network policy",
                PreflightStatus.WARN,
                "Host network is shared for LAN inference",
                "Bubblewrap --share-net preserves host networking and does not restrict egress to the Ornith endpoint.",
            )
        )
        checks.append(
            PreflightCheck(
                "confinement-runtime",
                "Sandbox confinement proof",
                PreflightStatus.PENDING,
                "Requires target-machine gate",
                "Filesystem, symlink, socket and child-process escape attempts are intentionally not claimed from static inspection.",
            )
        )

        environment = (
            ("HOME", "/tmp/pi-ui-preflight-home"),
            ("LANG", "C.UTF-8"),
            ("PATH", f"{settings.runtime_root}/bin:/usr/bin:/bin"),
            ("PI_OFFLINE", "1"),
            ("PI_SKIP_VERSION_CHECK", "1"),
        )
        return PreflightPlan(
            checks=tuple(checks),
            probes=tuple(probes),
            environment=environment,
        )

    @staticmethod
    def _add_executable_check(
        checks: list[PreflightCheck],
        probes: list[CommandProbe],
        *,
        check_id: str,
        label: str,
        executable: str,
        arguments: tuple[str, ...],
        required: bool,
    ) -> None:
        path = Path(executable)
        available = path.is_file() and os.access(path, os.X_OK)
        if available:
            checks.append(
                PreflightCheck(
                    check_id,
                    label,
                    PreflightStatus.PENDING,
                    "Version probe pending",
                    str(path),
                )
            )
            probes.append(
                CommandProbe(
                    probe_id=check_id,
                    label=label,
                    executable=str(path),
                    arguments=arguments,
                    required=required,
                )
            )
            return
        checks.append(
            PreflightCheck(
                check_id,
                label,
                PreflightStatus.FAIL if required else PreflightStatus.WARN,
                "Executable is unavailable",
                str(path),
            )
        )

    @staticmethod
    def _models_check(existing: ExistingModelsConfig | None) -> PreflightCheck:
        if existing is None:
            return PreflightCheck(
                "models-config",
                "Pi model configuration",
                PreflightStatus.FAIL,
                "No workspace model configuration was inspected",
            )
        if not existing.profiles:
            return PreflightCheck(
                "models-config",
                "Pi model configuration",
                PreflightStatus.FAIL,
                "No usable model profiles discovered",
                f"state={existing.management_state}",
            )
        if existing.management_state == ModelConfigManagementState.CHANGED_EXTERNALLY:
            return PreflightCheck(
                "models-config",
                "Pi model configuration",
                PreflightStatus.WARN,
                f"{len(existing.profiles)} profile(s) found but managed fingerprint changed",
                "Pi_UI will not overwrite or silently adopt the file.",
            )
        return PreflightCheck(
            "models-config",
            "Pi model configuration",
            PreflightStatus.PASS,
            f"{len(existing.profiles)} usable profile(s) discovered",
            f"state={existing.management_state}",
        )


def classify_probe_result(
    probe: CommandProbe,
    result: CommandProbeResult,
) -> PreflightCheck:
    """Turn a process result into a presentation-ready preflight check."""

    if result.start_error:
        return PreflightCheck(
            probe.probe_id,
            probe.label,
            PreflightStatus.FAIL if probe.required else PreflightStatus.WARN,
            "Version probe could not start",
            _limit(result.start_error),
        )
    if result.timed_out:
        return PreflightCheck(
            probe.probe_id,
            probe.label,
            PreflightStatus.FAIL if probe.required else PreflightStatus.WARN,
            f"Version probe exceeded {probe.timeout_ms} ms",
        )
    output = _first_text(result.stdout, result.stderr)
    if result.exit_code == 0:
        return PreflightCheck(
            probe.probe_id,
            probe.label,
            PreflightStatus.PASS,
            output or "Version probe succeeded",
            probe.executable,
        )
    return PreflightCheck(
        probe.probe_id,
        probe.label,
        PreflightStatus.FAIL if probe.required else PreflightStatus.WARN,
        f"Version probe exited with code {result.exit_code}",
        output,
    )


def sanitized_manifest_json(
    checks: tuple[PreflightCheck, ...],
    facts: HostRuntimeFacts,
) -> str:
    """Serialize shareable diagnostics without workspace paths or secrets."""

    public_checks = []
    for check in checks:
        item = asdict(check)
        item["status"] = str(check.status)
        if check.check_id in {"workspace", "bubblewrap", "pi", "runtime-root", "node"}:
            item["detail"] = "<local-path>" if check.detail else ""
        public_checks.append(item)
    payload = {
        "schema": 1,
        "runtime": {
            "os": facts.os_name,
            "osRelease": facts.os_release,
            "python": facts.python_version,
            "pyside6": facts.pyside_version,
            "qt": facts.qt_version,
        },
        "checks": public_checks,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _first_text(stdout: str, stderr: str) -> str:
    for source in (stdout, stderr):
        for line in source.splitlines():
            value = line.strip()
            if value:
                return _limit(value)
    return ""


def _limit(value: str) -> str:
    return value[:_MAX_PROBE_TEXT]
