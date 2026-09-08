from __future__ import annotations

from pathlib import Path

from core.agent.runtime import PiRuntimePaths, build_launch_spec
from core.settings import AgentSettings


def test_launch_spec_isolates_pi_config_and_sessions() -> None:
    paths = PiRuntimePaths(
        config_dir=Path("/data/pi-ui/pi-agent"),
        session_dir=Path("/state/pi-ui/sessions"),
    )
    spec = build_launch_spec(
        AgentSettings(
            executable="/opt/pi/bin/pi",
            provider="ornith-lan",
            model="ornith-1.5",
            thinking_level="high",
        ),
        working_directory=Path("/workspace"),
        paths=paths,
        base_environment={"PATH": "/usr/bin", "PI_OFFLINE": "1"},
    )

    assert spec.executable == "/opt/pi/bin/pi"
    assert spec.arguments == (
        "--mode",
        "rpc",
        "--session-dir",
        "/state/pi-ui/sessions",
        "--provider",
        "ornith-lan",
        "--model",
        "ornith-1.5",
        "--thinking",
        "high",
    )
    assert spec.environment["PI_CODING_AGENT_DIR"] == "/data/pi-ui/pi-agent"
    assert spec.environment["PI_CODING_AGENT_SESSION_DIR"] == "/state/pi-ui/sessions"
    assert spec.environment["PI_SKIP_VERSION_CHECK"] == "1"
    assert "PI_OFFLINE" not in spec.environment
    assert spec.working_directory == Path("/workspace")


def test_launch_spec_can_enable_offline_startup_and_upstream_version_check() -> None:
    spec = build_launch_spec(
        AgentSettings(skip_version_check=False, offline_startup=True),
        working_directory=Path("/workspace"),
        paths=PiRuntimePaths(Path("/cfg"), Path("/sessions")),
        base_environment={"PI_SKIP_VERSION_CHECK": "1"},
    )

    assert spec.environment["PI_OFFLINE"] == "1"
    assert "PI_SKIP_VERSION_CHECK" not in spec.environment
