from __future__ import annotations

import json
from pathlib import Path

from core.agent.model_config import PiModelsConfigManager
from core.agent.model_discovery import (
    ExistingAuthKind,
    ModelConfigManagementState,
    PiModelsConfigDiscovery,
)
from core.agent.runtime import PiRuntimePaths
from core.settings import AgentSettings


def test_missing_models_file_is_reported_without_creating_state(tmp_path: Path) -> None:
    paths = PiRuntimePaths.for_workspace(tmp_path)
    result = PiModelsConfigDiscovery().inspect(paths)

    assert result.management_state == ModelConfigManagementState.MISSING
    assert result.profiles == ()
    assert not (tmp_path / ".pi-agent").exists()


def test_unmanaged_existing_baseline_is_parsed_without_returning_secret(
    tmp_path: Path,
) -> None:
    paths = PiRuntimePaths.for_workspace(tmp_path)
    paths.host_agent_dir.mkdir()
    payload = {
        "providers": {
            "ornith-lan": {
                "baseUrl": "http://192.0.2.70:8080/v1",
                "api": "openai-completions",
                "apiKey": "$ORNITH_API_KEY",
                "compat": {
                    "supportsDeveloperRole": False,
                    "supportsReasoningEffort": True,
                },
                "models": [
                    {
                        "id": "Ornith",
                        "reasoning": True,
                        "input": ["text"],
                        "contextWindow": 131072,
                        "maxTokens": 32768,
                    },
                    {
                        "id": "Ornith-Vision",
                        "api": "anthropic-messages",
                        "input": ["text", "image"],
                        "compat": {"supportsReasoningEffort": False},
                    },
                ],
            }
        }
    }
    (paths.host_agent_dir / "models.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    result = PiModelsConfigDiscovery().inspect(paths)

    assert result.management_state == ModelConfigManagementState.UNMANAGED
    assert len(result.profiles) == 2
    first, second = result.profiles
    assert first.provider == "ornith-lan"
    assert first.model == "Ornith"
    assert first.base_url == "http://192.0.2.70:8080/v1"
    assert first.api == "openai-completions"
    assert first.auth_kind == ExistingAuthKind.ENV
    assert first.api_key_env == "ORNITH_API_KEY"
    assert first.context_window == 131072
    assert first.max_tokens == 32768
    assert first.reasoning is True
    assert first.supports_images is False
    assert first.supports_developer_role is False
    assert first.supports_reasoning_effort is True

    assert second.api == "anthropic-messages"
    assert second.supports_images is True
    assert second.supports_developer_role is False
    assert second.supports_reasoning_effort is False


def test_literal_api_key_is_classified_but_never_returned(tmp_path: Path) -> None:
    paths = PiRuntimePaths.for_workspace(tmp_path)
    paths.host_agent_dir.mkdir()
    secret = "super-secret-literal"
    (paths.host_agent_dir / "models.json").write_text(
        json.dumps(
            {
                "providers": {
                    "local": {
                        "baseUrl": "http://192.0.2.71:8080/v1",
                        "api": "openai-completions",
                        "apiKey": secret,
                        "models": [{"id": "model"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = PiModelsConfigDiscovery().inspect(paths)
    profile = result.profiles[0]

    assert profile.auth_kind == ExistingAuthKind.OTHER
    assert profile.api_key_env is None
    assert secret not in repr(result)


def test_pi_ui_managed_file_is_recognized_and_external_change_is_detected(
    tmp_path: Path,
) -> None:
    paths = PiRuntimePaths.for_workspace(tmp_path)
    manager = PiModelsConfigManager()
    manager.write(
        AgentSettings(
            provider="local",
            model="model",
            base_url="http://192.0.2.72:8080/v1",
        ),
        paths,
    )

    discovery = PiModelsConfigDiscovery()
    assert discovery.inspect(paths).management_state == ModelConfigManagementState.MANAGED

    target = paths.host_agent_dir / "models.json"
    target.write_text('{"changed":true}\n', encoding="utf-8")
    assert (
        discovery.inspect(paths).management_state
        == ModelConfigManagementState.CHANGED_EXTERNALLY
    )
