"""Build deterministic Pi RPC launch specifications."""

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
    """Raised when Pi cannot be launched with the requested runtime policy."""


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
    """Create only Pi_UI-owned runtime directories inside the AIOS root."""

    if not paths.host_workspace.is_dir():
        raise RuntimeConfigurationError(
            f"workspace does not exist or is not a directory: {paths.host_workspace}"
        )
    paths.host_agent_dir.mkdir(mode=0o700, exist_ok=True)
    paths.host_session_dir.mkdir(mode=0o700, exist_ok=True)


def build_launch_spec(
    settings: AgentSettings,
    *,
    working_directory: Path,
    paths: PiRuntimePaths | None = None,
    base_environment: Mapping[str, str] | None = None,
    session_id: str | None = None,
) -> PiLaunchSpec:
    """Create argv/environment for Pi RPC without invoking a shell.

    When sandboxing is enabled, QProcess launches Bubblewrap as the outer
    process and Bubblewrap execs Pi inside the AIOS mount namespace. The child
    environment is allow-listed here instead of inherited wholesale from the
    desktop session.

    ``session_id`` is Pi_UI's owned session identity. Pi 0.85.1's
    ``--session-id`` reopens that exact project session when it exists and
    creates a new session with the same id when the backing session file was
    deleted. This avoids both global-recency selection and brittle stale-file
    recovery in Pi_UI.
    """

    if session_id is not None and not is_valid_session_id(session_id):
        raise RuntimeConfigurationError("invalid Pi session id")

    runtime_paths = paths or PiRuntimePaths.for_workspace(working_directory)
    base_env = dict(os.environ if base_environment is None else base_environment)

    environment = _build_sanitized_environment(
        settings,
        base_environment=base_env,
        paths=runtime_paths,
    )
    pi_arguments = _build_pi_arguments(
        settings,
        runtime_paths,
        session_id=session_id,
    )

    if not settings.sandbox_enabled:
        return PiLaunchSpec(
            executable=settings.executable,
            arguments=tuple(pi_arguments),
            environment=environment,
            working_directory=runtime_paths.host_workspace,
            paths=runtime_paths,
        )

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
    if settings.sandbox_enabled:
        home = str(SANDBOX_HOME)
        path = f"{settings.runtime_root}/bin:/usr/bin:/bin"
        agent_dir = str(paths.sandbox_agent_dir)
        session_dir = str(paths.sandbox_session_dir)
        identity_environment = {
            "USER": "aios",
            "LOGNAME": "aios",
            "TMPDIR": "/tmp",
        }
    else:
        home = base_environment.get("HOME", str(Path.home()))
        path = base_environment.get("PATH", "/usr/bin:/bin")
        agent_dir = str(paths.host_agent_dir)
        session_dir = str(paths.host_session_dir)
        identity_environment = {}

    env = {
        "HOME": home,
        "PATH": path,
        "LANG": base_environment.get("LANG", "C.UTF-8"),
        "PI_CODING_AGENT_DIR": agent_dir,
        "PI_CODING_AGENT_SESSION_DIR": session_dir,
        "PI_TELEMETRY": "0",
        **identity_environment,
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
    session_dir = (
        str(paths.sandbox_session_dir)
        if settings.sandbox_enabled
        else str(paths.host_session_dir)
    )
    arguments = ["--mode", "rpc", "--session-dir", session_dir]
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
