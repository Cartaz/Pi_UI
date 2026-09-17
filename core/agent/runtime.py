"""Build deterministic, always-sandboxed Pi RPC launch specifications."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping

from core.sandbox import SANDBOX_HOME, build_bubblewrap_arguments
from core.session_id import is_valid_session_id
from core.settings import AgentSettings

SANDBOX_WORKSPACE = PurePosixPath("/workspace")
SANDBOX_AGENT_DIR = SANDBOX_WORKSPACE / ".pi-agent"
SANDBOX_SESSION_DIR = SANDBOX_AGENT_DIR / "sessions"


class RuntimeConfigurationError(ValueError):
    """Raised when Pi cannot be launched with the required sandbox policy."""


@dataclass(frozen=True, slots=True)
class PiRuntimePaths:
    host_workspace: Path
    host_agent_dir: Path
    host_session_dir: Path
    sandbox_workspace: PurePosixPath = SANDBOX_WORKSPACE
    sandbox_agent_dir: PurePosixPath = SANDBOX_AGENT_DIR
    sandbox_session_dir: PurePosixPath = SANDBOX_SESSION_DIR

    @classmethod
    def for_workspace(cls, workspace: Path) -> "PiRuntimePaths":
        host_workspace = workspace.expanduser().resolve()
        host_agent_dir = host_workspace / ".pi-agent"
        return cls(
            host_workspace=host_workspace,
            host_agent_dir=host_agent_dir,
            host_session_dir=host_agent_dir / "sessions",
        )


@dataclass(frozen=True, slots=True)
class PiLaunchSpec:
    """Complete outer-process specification consumed by QProcess."""

    executable: str
    arguments: tuple[str, ...]
    environment: dict[str, str]
    working_directory: Path
    paths: PiRuntimePaths


def prepare_runtime_paths(paths: PiRuntimePaths) -> None:
    """Create only Pi_UI-owned state, refusing redirected state directories."""

    if not paths.host_workspace.is_dir():
        raise RuntimeConfigurationError(
            f"workspace does not exist or is not a directory: {paths.host_workspace}"
        )
    for directory in (paths.host_agent_dir, paths.host_session_dir):
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise RuntimeConfigurationError(f"Pi runtime state must be a real directory: {directory}")
        directory.mkdir(mode=0o700, exist_ok=True)
        if directory.is_symlink():
            raise RuntimeConfigurationError(f"Pi runtime state was redirected: {directory}")


def build_launch_spec(
    settings: AgentSettings,
    *,
    working_directory: Path,
    paths: PiRuntimePaths | None = None,
    base_environment: Mapping[str, str] | None = None,
    session_id: str | None = None,
) -> PiLaunchSpec:
    """Create sandbox argv/environment without shell or direct-launch fallback.

    ``session_id`` belongs to Pi_UI. The pinned Pi 0.85.1 ``--session-id``
    resumes that exact project session or recreates the missing backing file.
    """

    if not settings.sandbox_enabled:
        raise RuntimeConfigurationError("Bubblewrap is mandatory; direct Pi launch is disabled")
    if session_id is not None and not is_valid_session_id(session_id):
        raise RuntimeConfigurationError("invalid Pi session id")

    runtime_paths = paths or PiRuntimePaths.for_workspace(working_directory)
    base_env = dict(os.environ if base_environment is None else base_environment)
    environment = _build_sanitized_environment(
        settings,
        base_environment=base_env,
        paths=runtime_paths,
    )
    pi_arguments = _build_pi_arguments(settings, runtime_paths, session_id=session_id)
    executable = _validated_sandbox_pi_executable(settings)
    arguments = build_bubblewrap_arguments(
        settings,
        host_workspace=runtime_paths.host_workspace,
        sandbox_workspace=runtime_paths.sandbox_workspace,
        command=(str(executable), *pi_arguments),
    )
    return PiLaunchSpec(
        executable=settings.bubblewrap_executable,
        arguments=arguments,
        environment=environment,
        working_directory=runtime_paths.host_workspace,
        paths=runtime_paths,
    )


def _build_sanitized_environment(
    settings: AgentSettings,
    *,
    base_environment: Mapping[str, str],
    paths: PiRuntimePaths,
) -> dict[str, str]:
    """Allow-list only the environment actually needed by sandboxed Pi."""

    env = {
        "HOME": str(SANDBOX_HOME),
        "PATH": f"{settings.runtime_root}/bin:/usr/bin:/bin",
        "LANG": base_environment.get("LANG", "C.UTF-8"),
        "PI_CODING_AGENT_DIR": str(paths.sandbox_agent_dir),
        "PI_CODING_AGENT_SESSION_DIR": str(paths.sandbox_session_dir),
        "PI_TELEMETRY": "0",
        "USER": "aios",
        "LOGNAME": "aios",
        "TMPDIR": "/tmp",
    }
    if settings.skip_version_check:
        env["PI_SKIP_VERSION_CHECK"] = "1"
    if settings.offline_startup:
        env["PI_OFFLINE"] = "1"
    if settings.auth_mode == "env" and settings.api_key_env:
        secret = base_environment.get(settings.api_key_env)
        if secret:
            env[settings.api_key_env] = secret
    return env


def _build_pi_arguments(
    settings: AgentSettings,
    paths: PiRuntimePaths,
    *,
    session_id: str | None,
) -> list[str]:
    arguments = ["--mode", "rpc", "--session-dir", str(paths.sandbox_session_dir)]
    if session_id is not None:
        arguments.extend(("--session-id", session_id))
    if settings.provider:
        arguments.extend(("--provider", settings.provider))
    if settings.model:
        arguments.extend(("--model", settings.model))
    if settings.thinking_level:
        arguments.extend(("--thinking", settings.thinking_level))
    return arguments


def _validated_sandbox_pi_executable(settings: AgentSettings) -> PurePosixPath:
    runtime_root = PurePosixPath(settings.runtime_root)
    executable = PurePosixPath(settings.executable)
    if not runtime_root.is_absolute() or not executable.is_absolute():
        raise RuntimeConfigurationError(
            "sandbox runtime_root and Pi executable must be absolute paths"
        )
    try:
        executable.relative_to(runtime_root)
    except ValueError as exc:
        raise RuntimeConfigurationError(
            "sandboxed Pi executable must live inside runtime_root"
        ) from exc
    return executable
