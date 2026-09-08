from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.agent.bootstrap import (
    ExistingRuntimeChangedError,
    ExistingRuntimeProfileError,
    MissingRuntimeCredentialError,
    PiRuntimeBootstrap,
    RuntimeModelConfigSource,
)
from core.agent.model_config import UnmanagedModelsConfigError
from core.agent.model_discovery import PiModelsConfigDiscovery
from core.agent.runtime import PiRuntimePaths
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

    assert prepared.models_config is not None
    models = json.loads(prepared.models_config.path.read_text(encoding="utf-8"))
    assert prepared.config_source == RuntimeModelConfigSource.DERIVED
    assert prepared.config_sha256 is None
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

    assert prepared.models_config is not None
    assert prepared.models_config.path.is_file()


def test_existing_user_models_config_stops_managed_bootstrap_without_overwrite(
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


def test_existing_baseline_can_launch_without_rewriting_models_file(
    tmp_path: Path,
) -> None:
    paths = PiRuntimePaths.for_workspace(tmp_path)
    paths.host_agent_dir.mkdir()
    target = paths.host_agent_dir / "models.json"
    original = json.dumps(
        {
            "providers": {
                "ornith-lan": {
                    "baseUrl": "http://192.0.2.64:8080/v1",
                    "api": "openai-completions",
                    "apiKey": "$ORNITH_API_KEY",
                    "models": [{"id": "Ornith", "contextWindow": 131072}],
                }
            }
        }
    )
    target.write_text(original, encoding="utf-8")

    discovery = PiModelsConfigDiscovery().inspect(paths)
    assert discovery.sha256 is not None
    profile = discovery.profiles[0]

    prepared = PiRuntimeBootstrap().prepare_existing(
        AgentSettings(thinking_level="high"),
        workspace=tmp_path,
        profile=profile,
        expected_sha256=discovery.sha256,
        base_environment={
            "USER": "tester",
            "ORNITH_API_KEY": "secret-value",
        },
    )

    assert prepared.models_config is None
    assert prepared.config_source == RuntimeModelConfigSource.EXISTING
    assert prepared.config_sha256 == discovery.sha256
    assert target.read_text(encoding="utf-8") == original
    assert prepared.launch_spec.environment["ORNITH_API_KEY"] == "secret-value"
    separator = prepared.launch_spec.arguments.index("--")
    assert prepared.launch_spec.arguments[separator + 1 :] == (
        "/opt/pi-agent/bin/pi",
        "--mode",
        "rpc",
        "--session-dir",
        "/workspace/.pi-agent/sessions",
        "--provider",
        "ornith-lan",
        "--model",
        "Ornith",
        "--thinking",
        "high",
    )


def test_existing_literal_auth_can_be_reused_without_exposing_secret(
    tmp_path: Path,
) -> None:
    paths = PiRuntimePaths.for_workspace(tmp_path)
    paths.host_agent_dir.mkdir()
    secret = "literal-secret-in-existing-file"
    target = paths.host_agent_dir / "models.json"
    target.write_text(
        json.dumps(
            {
                "providers": {
                    "local": {
                        "baseUrl": "http://192.0.2.65:8080/v1",
                        "api": "openai-completions",
                        "apiKey": secret,
                        "models": [{"id": "model"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    discovered = PiModelsConfigDiscovery().inspect(paths)
    assert discovered.sha256 is not None

    prepared = PiRuntimeBootstrap().prepare_existing(
        AgentSettings(),
        workspace=tmp_path,
        profile=discovered.profiles[0],
        expected_sha256=discovered.sha256,
        base_environment={"USER": "tester"},
    )

    assert secret not in prepared.launch_spec.environment.values()
    assert secret not in "\0".join(prepared.launch_spec.arguments)
    assert target.read_text(encoding="utf-8").find(secret) >= 0


def test_existing_baseline_hash_change_blocks_launch(tmp_path: Path) -> None:
    paths = PiRuntimePaths.for_workspace(tmp_path)
    paths.host_agent_dir.mkdir()
    target = paths.host_agent_dir / "models.json"
    target.write_text(
        json.dumps(
            {
                "providers": {
                    "local": {
                        "baseUrl": "http://192.0.2.66:8080/v1",
                        "api": "openai-completions",
                        "apiKey": "pi-ui-local",
                        "models": [{"id": "model"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    discovered = PiModelsConfigDiscovery().inspect(paths)
    assert discovered.sha256 is not None
    profile = discovered.profiles[0]
    target.write_text('{"providers":{}}\n', encoding="utf-8")

    with pytest.raises(ExistingRuntimeChangedError, match="changed"):
        PiRuntimeBootstrap().prepare_existing(
            AgentSettings(),
            workspace=tmp_path,
            profile=profile,
            expected_sha256=discovered.sha256,
            base_environment={"USER": "tester"},
        )


def test_existing_profile_must_still_be_present_at_launch(tmp_path: Path) -> None:
    paths = PiRuntimePaths.for_workspace(tmp_path)
    paths.host_agent_dir.mkdir()
    target = paths.host_agent_dir / "models.json"
    target.write_text(
        json.dumps(
            {
                "providers": {
                    "local": {
                        "baseUrl": "http://192.0.2.67:8080/v1",
                        "api": "openai-completions",
                        "apiKey": "pi-ui-local",
                        "models": [{"id": "model"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    discovered = PiModelsConfigDiscovery().inspect(paths)
    assert discovered.sha256 is not None
    original_profile = discovered.profiles[0]

    fabricated = type(original_profile)(
        provider=original_profile.provider,
        model="not-there",
        base_url=original_profile.base_url,
        api=original_profile.api,
        auth_kind=original_profile.auth_kind,
        api_key_env=original_profile.api_key_env,
        context_window=original_profile.context_window,
        max_tokens=original_profile.max_tokens,
        reasoning=original_profile.reasoning,
        supports_images=original_profile.supports_images,
        supports_developer_role=original_profile.supports_developer_role,
        supports_reasoning_effort=original_profile.supports_reasoning_effort,
    )

    with pytest.raises(ExistingRuntimeProfileError, match="no longer present"):
        PiRuntimeBootstrap().prepare_existing(
            AgentSettings(),
            workspace=tmp_path,
            profile=fabricated,
            expected_sha256=discovered.sha256,
            base_environment={"USER": "tester"},
        )
