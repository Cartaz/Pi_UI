"""Reusable fail-closed Bubblewrap mount policy shared by Pi and confinement gates."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from core.settings import AgentSettings

SANDBOX_HOME = PurePosixPath("/home/aios")
SANDBOX_AGENT_STATE = PurePosixPath("/workspace/.pi-agent")

_UNSAFE_RUNTIME_ROOTS = frozenset(
    {
        PurePosixPath("/"),
        PurePosixPath("/home"),
        PurePosixPath("/root"),
        PurePosixPath("/run"),
        PurePosixPath("/etc"),
        PurePosixPath("/var"),
        PurePosixPath("/tmp"),
        PurePosixPath("/mnt"),
        PurePosixPath("/media"),
        PurePosixPath("/opt"),
        PurePosixPath("/srv"),
        PurePosixPath("/usr"),
        PurePosixPath("/usr/local"),
    }
)


class SandboxConfigurationError(ValueError):
    """Raised when a command cannot be represented inside the sandbox policy."""


def validate_sandbox_paths(
    settings: AgentSettings,
    *,
    host_workspace: Path,
) -> tuple[Path, PurePosixPath]:
    """Validate canonical workspace/runtime roots and the private writable mount."""

    if not settings.sandbox_enabled:
        raise SandboxConfigurationError("Bubblewrap is mandatory for Pi_UI")

    runtime_root = PurePosixPath(settings.runtime_root)
    if not runtime_root.is_absolute():
        raise SandboxConfigurationError("sandbox runtime_root must be an absolute path")
    if runtime_root in _UNSAFE_RUNTIME_ROOTS:
        raise SandboxConfigurationError(
            "runtime_root is too broad for the Pi_UI confinement policy"
        )

    workspace = host_workspace.expanduser().resolve()
    runtime_host = Path(settings.runtime_root).expanduser().resolve()
    if _paths_overlap(runtime_host, workspace):
        raise SandboxConfigurationError(
            "runtime_root must not overlap the AIOS workspace"
        )

    # The only writable bind in the workspace is application-owned Pi state.
    # Do not allow a pre-existing symlink to redirect it to another host tree.
    agent_state = workspace / ".pi-agent"
    if agent_state.is_symlink() or (agent_state.exists() and not agent_state.is_dir()):
        raise SandboxConfigurationError("Pi agent state must be a real directory")
    return workspace, runtime_root


def build_bubblewrap_arguments(
    settings: AgentSettings,
    *,
    host_workspace: Path,
    sandbox_workspace: PurePosixPath,
    command: Sequence[str],
) -> tuple[str, ...]:
    """Build argv without a shell; no unconfined fallback or unversioned file writes.

    Until pre-write revisions and conflict handling cover every Pi tool, the
    document workspace is read-only. Only its dedicated ``.pi-agent`` state
    directory is writable so Pi can create/resume sessions and configuration.
    The bootstrap/gate must create that directory before launching Bubblewrap.
    Network remains shared for LAN inference and optional internet tool use;
    this mount policy is *not* an egress firewall.
    """

    if not command or not isinstance(command[0], str) or not command[0]:
        raise SandboxConfigurationError("sandbox command requires an executable")

    workspace, runtime_root = validate_sandbox_paths(
        settings,
        host_workspace=host_workspace,
    )
    command_executable = PurePosixPath(command[0])
    if not command_executable.is_absolute():
        raise SandboxConfigurationError("sandbox command executable must be absolute")
    if not _command_is_mounted(command_executable, runtime_root):
        raise SandboxConfigurationError(
            "sandbox command executable must be inside /usr or runtime_root"
        )
    if sandbox_workspace != PurePosixPath("/workspace"):
        raise SandboxConfigurationError("sandbox workspace must be /workspace")

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
        str(SANDBOX_HOME),
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
        "--ro-bind",
        str(workspace),
        str(sandbox_workspace),
        "--bind",
        str(workspace / ".pi-agent"),
        str(SANDBOX_AGENT_STATE),
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
    if root in _UNSAFE_RUNTIME_ROOTS:
        return path.is_relative_to(PurePosixPath("/usr"))
    return _command_is_mounted(path, root)


def _command_is_mounted(executable: PurePosixPath, runtime_root: PurePosixPath) -> bool:
    for root in (PurePosixPath("/usr"), runtime_root):
        try:
            executable.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _paths_overlap(first: Path, second: Path) -> bool:
    if first == second:
        return True
    return first in second.parents or second in first.parents
