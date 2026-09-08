"""Build a deterministic, app-isolated Pi RPC launch specification."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from core.settings import AgentSettings, default_data_dir, default_state_dir


@dataclass(frozen=True, slots=True)
class PiRuntimePaths:
    config_dir: Path
    session_dir: Path

    @classmethod
    def defaults(cls) -> "PiRuntimePaths":
        return cls(
            config_dir=default_data_dir() / "pi-agent",
            session_dir=default_state_dir() / "sessions",
        )


@dataclass(frozen=True, slots=True)
class PiLaunchSpec:
    executable: str
    arguments: tuple[str, ...]
    environment: dict[str, str]
    working_directory: Path
    paths: PiRuntimePaths


def build_launch_spec(
    settings: AgentSettings,
    *,
    working_directory: Path,
    paths: PiRuntimePaths | None = None,
    base_environment: Mapping[str, str] | None = None,
) -> PiLaunchSpec:
    """Create argv/environment for ``pi --mode rpc`` without invoking a shell."""

    runtime_paths = paths or PiRuntimePaths.defaults()
    env = dict(os.environ if base_environment is None else base_environment)

    env["PI_CODING_AGENT_DIR"] = str(runtime_paths.config_dir)
    env["PI_CODING_AGENT_SESSION_DIR"] = str(runtime_paths.session_dir)

    if settings.skip_version_check:
        env["PI_SKIP_VERSION_CHECK"] = "1"
    else:
        env.pop("PI_SKIP_VERSION_CHECK", None)

    if settings.offline_startup:
        env["PI_OFFLINE"] = "1"
    else:
        env.pop("PI_OFFLINE", None)

    arguments: list[str] = [
        "--mode",
        "rpc",
        "--session-dir",
        str(runtime_paths.session_dir),
    ]
    if settings.provider:
        arguments.extend(("--provider", settings.provider))
    if settings.model:
        arguments.extend(("--model", settings.model))
    if settings.thinking_level:
        arguments.extend(("--thinking", settings.thinking_level))

    return PiLaunchSpec(
        executable=settings.executable,
        arguments=tuple(arguments),
        environment=env,
        working_directory=working_directory,
        paths=runtime_paths,
    )
