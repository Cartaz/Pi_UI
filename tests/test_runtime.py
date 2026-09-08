from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from core.agent.runtime import (
    PiRuntimePaths,
    RuntimeConfigurationError,
    build_launch_spec,
    prepare_runtime_paths,
)
from core.settings import AgentSettings


def test_sandbox_launch_spec_matches_aios_confinement(tmp_path: Path) -> None:
    secret_name = "PI_UI_TEST_KEY"
    spec = build_launch_spec(
        AgentSettings(
            provider="ornith-lan",
            model="ornith-1.5",
            thinking_level="high",
            api_key_env=secret_name,
        ),
        working_directory=tmp_path,
        base_environment={
            "USER": "tester",
            "HOME": "/home/tester-real",
            "PATH": "/host/private/bin:/usr/bin",
            "LANG": "it_IT.UTF-8",
            secret_name: "not-on-the-command-line",
            "SSH_AUTH_SOCK": "/run/user/1000/ssh-agent",
            "DISPLAY": ":0",
        },
    )

    assert spec.executable == "/usr/bin/bwrap"
    assert spec.working_directory == tmp_path.resolve()
    assert spec.paths.host_agent_dir == tmp_path.resolve() / ".pi-agent"
    assert spec.paths.host_session_dir == tmp_path.resolve() / ".pi-agent/sessions"

    args = spec.arguments
    assert args[:4] == (
        "--unshare-all",
        "--share-net",
        "--die-with-parent",
        "--new-session",
    )
    assert ("--ro-bind", "/usr", "/usr") == args[4:7]
    assert "--tmpfs" in args
    assert "/home" in args
    assert "/home/tester" in args

    bind_index = args.index("--bind")
    assert args[bind_index + 1 : bind_index + 3] == (
        str(tmp_path.resolve()),
        "/workspace",
    )
    separator = args.index("--")
    assert args[separator + 1 :] == (
        "/opt/pi-agent/bin/pi",
        "--mode",
        "rpc",
        "--session-dir",
        "/workspace/.pi-agent/sessions",
        "--provider",
        "ornith-lan",
        "--model",
        "ornith-1.5",
        "--thinking",
        "high",
    )

    assert spec.environment == {
        "HOME": "/home/tester",
        "PATH": "/opt/pi-agent/bin:/usr/bin:/bin",
        "LANG": "it_IT.UTF-8",
        "PI_CODING_AGENT_DIR": "/workspace/.pi-agent",
        "PI_CODING_AGENT_SESSION_DIR": "/workspace/.pi-agent/sessions",
        "PI_SKIP_VERSION_CHECK": "1",
        secret_name: "not-on-the-command-line",
    }
    assert "SSH_AUTH_SOCK" not in spec.environment
    assert "DISPLAY" not in spec.environment
    assert "not-on-the-command-line" not in "\0".join(args)


def test_prepare_runtime_paths_creates_only_hidden_pi_state(tmp_path: Path) -> None:
    paths = PiRuntimePaths.for_workspace(tmp_path)
    prepare_runtime_paths(paths)

    assert paths.host_agent_dir.is_dir()
    assert paths.host_session_dir.is_dir()
    assert sorted(item.name for item in tmp_path.iterdir()) == [".pi-agent"]


def test_prepare_runtime_paths_rejects_missing_workspace(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(RuntimeConfigurationError, match="workspace does not exist"):
        prepare_runtime_paths(PiRuntimePaths.for_workspace(missing))


def test_direct_launch_is_explicit_and_uses_host_paths(tmp_path: Path) -> None:
    settings = replace(
        AgentSettings(),
        sandbox_enabled=False,
        executable="/opt/pi-agent/bin/pi",
        skip_version_check=False,
        offline_startup=True,
    )
    spec = build_launch_spec(
        settings,
        working_directory=tmp_path,
        base_environment={
            "HOME": "/home/tester-real",
            "PATH": "/usr/local/bin:/usr/bin",
            "USER": "tester",
        },
    )

    assert spec.executable == "/opt/pi-agent/bin/pi"
    assert spec.arguments[:4] == (
        "--mode",
        "rpc",
        "--session-dir",
        str(tmp_path.resolve() / ".pi-agent/sessions"),
    )
    assert spec.environment["HOME"] == "/home/tester-real"
    assert spec.environment["PATH"] == "/usr/local/bin:/usr/bin"
    assert spec.environment["PI_CODING_AGENT_DIR"] == str(
        tmp_path.resolve() / ".pi-agent"
    )
    assert spec.environment["PI_OFFLINE"] == "1"
    assert "PI_SKIP_VERSION_CHECK" not in spec.environment
