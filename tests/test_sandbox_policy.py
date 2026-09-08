from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from core.sandbox import (
    SandboxConfigurationError,
    build_bubblewrap_arguments,
    command_is_visible_in_sandbox,
)
from core.settings import AgentSettings


def test_canonical_policy_exposes_only_declared_runtime_and_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "AIOS"
    workspace.mkdir()
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    settings = AgentSettings(
        executable=str(runtime_root / "bin" / "pi"),
        runtime_root=str(runtime_root),
        bubblewrap_executable=str(tmp_path / "bwrap"),
    )
    command = (str(runtime_root / "bin" / "node"), "/workspace/probe.mjs")

    args = build_bubblewrap_arguments(
        settings,
        host_workspace=workspace,
        sandbox_workspace=PurePosixPath("/workspace"),
        sandbox_home=PurePosixPath("/home/tester"),
        command=command,
    )

    assert args[:4] == (
        "--unshare-all",
        "--share-net",
        "--die-with-parent",
        "--new-session",
    )
    assert _contains_triplet(args, "--ro-bind", "/usr", "/usr")
    assert _contains_triplet(args, "--ro-bind", str(runtime_root), str(runtime_root))
    assert _contains_triplet(args, "--bind", str(workspace.resolve()), "/workspace")
    assert "/run/user" not in args
    assert str(tmp_path.parent) not in args
    separator = args.index("--")
    assert args[separator + 1 :] == command


def test_command_visibility_matches_mounted_trees(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"

    assert command_is_visible_in_sandbox(
        "/usr/bin/node",
        runtime_root=str(runtime_root),
    )
    assert command_is_visible_in_sandbox(
        str(runtime_root / "bin" / "node"),
        runtime_root=str(runtime_root),
    )
    assert not command_is_visible_in_sandbox(
        str(tmp_path / "home" / "tester" / ".local" / "bin" / "node"),
        runtime_root=str(runtime_root),
    )
    assert not command_is_visible_in_sandbox(
        "node",
        runtime_root=str(runtime_root),
    )


def test_policy_rejects_command_from_unmounted_host_tree(tmp_path: Path) -> None:
    workspace = tmp_path / "AIOS"
    workspace.mkdir()
    runtime_root = tmp_path / "runtime"
    settings = AgentSettings(
        executable=str(runtime_root / "bin" / "pi"),
        runtime_root=str(runtime_root),
    )

    with pytest.raises(SandboxConfigurationError, match="inside /usr or runtime_root"):
        build_bubblewrap_arguments(
            settings,
            host_workspace=workspace,
            sandbox_workspace=PurePosixPath("/workspace"),
            sandbox_home=PurePosixPath("/home/tester"),
            command=(str(tmp_path / "private" / "node"),),
        )


@pytest.mark.parametrize(
    "runtime_root",
    [
        "/",
        "/home",
        "/root",
        "/run",
        "/etc",
        "/var",
        "/tmp",
        "/mnt",
        "/media",
        "/opt",
        "/srv",
        "/usr",
        "/usr/local",
    ],
)
def test_policy_rejects_overbroad_runtime_mounts(tmp_path: Path, runtime_root: str) -> None:
    workspace = tmp_path / "AIOS"
    workspace.mkdir()
    settings = AgentSettings(
        executable=f"{runtime_root.rstrip('/')}/bin/pi" if runtime_root != "/" else "/bin/pi",
        runtime_root=runtime_root,
    )

    with pytest.raises(SandboxConfigurationError, match="too broad"):
        build_bubblewrap_arguments(
            settings,
            host_workspace=workspace,
            sandbox_workspace=PurePosixPath("/workspace"),
            sandbox_home=PurePosixPath("/home/tester"),
            command=(settings.executable,),
        )


def test_policy_rejects_runtime_overlapping_writable_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "AIOS"
    workspace.mkdir()
    runtime_root = workspace / ".runtime"
    settings = AgentSettings(
        executable=str(runtime_root / "bin" / "pi"),
        runtime_root=str(runtime_root),
    )

    with pytest.raises(SandboxConfigurationError, match="must not overlap"):
        build_bubblewrap_arguments(
            settings,
            host_workspace=workspace,
            sandbox_workspace=PurePosixPath("/workspace"),
            sandbox_home=PurePosixPath("/home/tester"),
            command=(settings.executable,),
        )


def _contains_triplet(args: tuple[str, ...], first: str, second: str, third: str) -> bool:
    return any(
        args[index : index + 3] == (first, second, third)
        for index in range(len(args) - 2)
    )
