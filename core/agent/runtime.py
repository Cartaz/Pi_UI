"""Build deterministic Pi RPC launch specifications."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping

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
    user_name: str | None = None,
) -> PiLaunchSpec:
    """Create argv/environment for Pi RPC without invoking a shell.

    When sandboxing is enabled, QProcess launches Bubblewrap as the outer
    process and Bubblewrap execs Pi inside the AIOS mount namespace. The child
    environment is allow-listed here instead of inherited wholesale from the
    desktop session.
    """

    runtime_paths = paths or PiRuntimePaths.for_workspace(working_directory)
    base_env = dict(os.environ if base_environment is None else base_environment)
    fake_user = user_name or base_env.get("USER") or "aios"
    sandbox_home = PurePosixPath("/home") / fake_user

    environment = _build_sanitized_environment(
        settings,
        base_environment=base_env,
        sandbox_home=sandbox_home,
        paths=runtime_paths,
    )
    pi_arguments = _build_pi_arguments(settings, runtime_paths)

    if not settings.sandbox_enabled:
        return PiLaunchSpec(
            executable=settings.executable,
            arguments=tuple(pi_arguments),
            environment=environment,
            working_directory=runtime_paths.host_workspace,
            paths=runtime_paths,
        )

    arguments = _build_bubblewrap_arguments(
        settings,
        paths=runtime_paths,
        sandbox_home=sandbox_home,
        pi_arguments=pi_arguments,
    )
    return PiLaunchSpec(
        executable=settings.bubblewrap_executable,
        arguments=tuple(arguments),
        environment=environment,
        working_directory=runtime_paths.host_workspace,
        paths=runtime_paths,
    )


def _build_sanitized_environment(
    settings: AgentSettings,
    *,
    base_environment: Mapping[str, str],
    sandbox_home: PurePosixPath,
    paths: PiRuntimePaths,
) -> dict[str, str]:
    if settings.sandbox_enabled:
        home = str(sandbox_home)
        path = f"{settings.runtime_root}/bin:/usr/bin:/bin"
        agent_dir = str(paths.sandbox_agent_dir)
        session_dir = str(paths.sandbox_session_dir)
    else:
        home = base_environment.get("HOME", str(Path.home()))
        path = base_environment.get("PATH", "/usr/bin:/bin")
        agent_dir = str(paths.host_agent_dir)
        session_dir = str(paths.host_session_dir)

    env = {
        "HOME": home,
        "PATH": path,
        "LANG": base_environment.get("LANG", "C.UTF-8"),
        "PI_CODING_AGENT_DIR": agent_dir,
        "PI_CODING_AGENT_SESSION_DIR": session_dir,
    }

    if settings.skip_version_check:
        env["PI_SKIP_VERSION_CHECK"] = "1"
    if settings.offline_startup:
        env["PI_OFFLINE"] = "1"

    if settings.api_key_env:
        secret = base_environment.get(settings.api_key_env)
        if secret:
            env[settings.api_key_env] = secret

    return env


def _build_pi_arguments(
    settings: AgentSettings,
    paths: PiRuntimePaths,
) -> list[str]:
    session_dir = (
        str(paths.sandbox_session_dir)
        if settings.sandbox_enabled
        else str(paths.host_session_dir)
    )
    arguments = ["--mode", "rpc", "--session-dir", session_dir]
    if settings.provider:
        arguments.extend(("--provider", settings.provider))
    if settings.model:
        arguments.extend(("--model", settings.model))
    if settings.thinking_level:
        arguments.extend(("--thinking", settings.thinking_level))
    return arguments


def _build_bubblewrap_arguments(
    settings: AgentSettings,
    *,
    paths: PiRuntimePaths,
    sandbox_home: PurePosixPath,
    pi_arguments: list[str],
) -> list[str]:
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

    return [
        "--unshare-all",
        "--share-net",
        "--die-with-parent",
        "--new-session",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/sbin",
        "/sbin",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--ro-bind",
        str(runtime_root),
        str(runtime_root),
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--tmpfs",
        "/home",
        "--dir",
        str(sandbox_home),
        "--dir",
        "/etc",
        "--ro-bind-try",
        "/etc/resolv.conf",
        "/etc/resolv.conf",
        "--ro-bind-try",
        "/etc/hosts",
        "/etc/hosts",
        "--ro-bind-try",
        "/etc/nsswitch.conf",
        "/etc/nsswitch.conf",
        "--ro-bind-try",
        "/etc/ssl/certs",
        "/etc/ssl/certs",
        "--ro-bind-try",
        "/etc/ca-certificates",
        "/etc/ca-certificates",
        "--bind",
        str(paths.host_workspace),
        str(paths.sandbox_workspace),
        "--chdir",
        str(paths.sandbox_workspace),
        "--",
        str(executable),
        *pi_arguments,
    ]
