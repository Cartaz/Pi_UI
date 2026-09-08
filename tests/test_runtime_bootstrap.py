from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.agent.bootstrap import MissingRuntimeCredentialError, PiRuntimeBootstrap
from core.agent.model_config import UnmanagedModelsConfigError
from core.settings import AgentSettings


def test_bootstrap_writes_model_config_and_builds_sandbox_launch(tmp_path: Path) -> None:
    settings = AgentSettings(
        provider="ornith-lan",
        model="Ornith",
        base_url="http://192.0.2.60:8080/v1",
        auth_mode="env",
        api_key_env="ORNITH_API_KEY",
    )

    prepared = PiRuntimeBootstrap().prepare(
        settings,
        workspace=tmp_path,
        base_environment={
            "USER": "tester",
            "LANG": "C.UTF-8",
            "ORNITH_API_KEY": "secret-value",
        },
    )

    models = json.loads(prepared.models_config.path.read_text(encoding="utf-8"))
    assert models["providers"]["ornith-lan"]["apiKey"] == "$ORNITH_API_KEY"
    assert prepared.launch_spec.executable == "/usr/bin/bwrap"
    assert prepared.launch_spec.environment["ORNITH_API_KEY"] == "secret-value"
    assert "secret-value" not in "\0".join(prepared.launch_spec.arguments)
    assert prepared.paths.host_workspace == tmp_path.resolve()


def test_missing_runtime_credential_fails_before_models_write(tmp_path: Path) -> None:
    settings = AgentSettings(
        provider="ornith-lan",
        model="Ornith",
        base_url="http://192.0.2.61:8080/v1",
        auth_mode="env",
        api_key_env="ORNITH_API_KEY",
    )

    with pytest.raises(MissingRuntimeCredentialError, match="ORNITH_API_KEY"):
        PiRuntimeBootstrap().prepare(
            settings,
            workspace=tmp_path,
            base_environment={"USER": "tester"},
        )

    assert not (tmp_path / ".pi-agent/models.json").exists()


def test_keyless_runtime_needs_no_credential(tmp_path: Path) -> None:
    prepared = PiRuntimeBootstrap().prepare(
        AgentSettings(
            provider="ornith-lan",
            model="Ornith",
            base_url="http://192.0.2.62:8080/v1",
            auth_mode="none",
        ),
        workspace=tmp_path,
        base_environment={"USER": "tester"},
    )

    assert prepared.models_config.path.is_file()


def test_existing_user_models_config_stops_bootstrap_without_overwrite(
    tmp_path: Path,
) -> None:
    agent_dir = tmp_path / ".pi-agent"
    agent_dir.mkdir()
    target = agent_dir / "models.json"
    original = '{"providers":{"existing":{}}}\n'
    target.write_text(original, encoding="utf-8")

    with pytest.raises(UnmanagedModelsConfigError):
        PiRuntimeBootstrap().prepare(
            AgentSettings(
                provider="ornith-lan",
                model="Ornith",
                base_url="http://192.0.2.63:8080/v1",
            ),
            workspace=tmp_path,
            base_environment={"USER": "tester"},
        )

    assert target.read_text(encoding="utf-8") == original
