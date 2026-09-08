from __future__ import annotations

from pathlib import Path

from controllers.agent_controller import AgentController, ConnectionState
from core.agent.model_discovery import (
    ModelConfigManagementState,
    PiModelsConfigDiscovery,
)
from core.agent.runtime import PiLaunchSpec, PiRuntimePaths
from core.settings import AppSettings, SettingsStore


def test_invalid_models_config_is_discovered_without_raising(tmp_path: Path) -> None:
    agent_dir = tmp_path / ".pi-agent"
    agent_dir.mkdir()
    target = agent_dir / "models.json"
    target.write_bytes(b"{not-json\xff")

    result = PiModelsConfigDiscovery().inspect(PiRuntimePaths.for_workspace(tmp_path))

    assert result.path == target
    assert result.sha256 is not None
    assert result.management_state == ModelConfigManagementState.CHANGED_EXTERNALLY
    assert result.profiles == ()


def test_controller_stays_open_but_blocks_connect_for_invalid_models_config(
    tmp_path: Path,
) -> None:
    agent_dir = tmp_path / ".pi-agent"
    agent_dir.mkdir()
    (agent_dir / "models.json").write_text("{broken", encoding="utf-8")

    store = SettingsStore(tmp_path / "app-settings.json")
    settings = AppSettings(workspace_root=str(tmp_path))

    def unexpected_transport(
        _launch_spec: PiLaunchSpec,
        _startup_timeout_ms: int,
        _shutdown_timeout_ms: int,
    ) -> object:
        raise AssertionError("transport must not be created for invalid models.json")

    controller = AgentController(store, unexpected_transport, settings=settings)

    assert controller.workspace == tmp_path.resolve()
    assert controller.connection_state == ConnectionState.DISCONNECTED
    assert controller.profiles == ()
    assert controller.selected_profile is None
    assert controller.can_connect is False
    assert "models.json found" in controller.status_text
