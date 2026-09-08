"""Reusable Bubblewrap mount policy shared by Pi runtime and M0 gates."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from core.settings import AgentSettings


class SandboxConfigurationError(ValueError):
    """Raised when a command cannot be represented inside the sandbox policy."""


def build_bubblewrap_arguments(
    settings: AgentSettings,
    *,
    host_workspace: Path,
    sandbox_workspace: PurePosixPath,
    sandbox_home: PurePosixPath,
    command: Sequence[str],
) -> tuple[str, ...]:
    """Build the canonical Pi_UI Bubblewrap argv without invoking a shell.

    The sandbox starts from an empty mount namespace. The AIOS workspace is the
    only personal read/write tree; ``/usr`` and the managed Pi runtime are
    read-only. Network remains shared intentionally so Pi can reach LAN
    inference and the internet when required by tools.
    """

    if not settings.sandbox_enabled:
        raise SandboxConfigurationError("Bubblewrap policy requires sandbox_enabled")
    if not command or not isinstance(command[0], str) or not command[0]:
        raise SandboxConfigurationError("sandbox command requires an executable")

    runtime_root = PurePosixPath(settings.runtime_root)
    command_executable = PurePosixPath(command[0])
    if not runtime_root.is_absolute() or not command_executable.is_absolute():
        raise SandboxConfigurationError(
            "sandbox runtime_root and command executable must be absolute paths"
        )
    if not _command_is_mounted(command_executable, runtime_root):
        raise SandboxConfigurationError(
            "sandbox command executable must be inside /usr or runtime_root"
        )

    workspace = host_workspace.expanduser().resolve()
    return (
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
        str(workspace),
        str(sandbox_workspace),
        "--chdir",
        str(sandbox_workspace),
        "--",
        *tuple(command),
    )


def command_is_visible_in_sandbox(
    executable: str,
    *,
    runtime_root: str,
) -> bool:
    """Return whether an absolute executable path belongs to a mounted tree."""

    path = PurePosixPath(executable)
    root = PurePosixPath(runtime_root)
    if not path.is_absolute() or not root.is_absolute():
        return False
    return _command_is_mounted(path, root)


def _command_is_mounted(executable: PurePosixPath, runtime_root: PurePosixPath) -> bool:
    for root in (PurePosixPath("/usr"), runtime_root):
        try:
            executable.relative_to(root)
            return True
        except ValueError:
            continue
    return False
