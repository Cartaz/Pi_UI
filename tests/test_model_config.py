from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core.agent.model_config import (
    LOCAL_AUTH_PLACEHOLDER,
    ModelConfigError,
    PiModelsConfigManager,
)
from core.agent.runtime import PiRuntimePaths
from core.settings import AgentSettings


def test_minimal_keyless_local_model_omits_unverified_capabilities() -> None:
    manager = PiModelsConfigManager()
    payload = manager.build_payload(
        AgentSettings(
            provider="ornith-lan",
            model="Ornith",
            base_url="http://192.0.2.10:8080/v1",
        )
    )

    assert payload == {
        "providers": {
            "ornith-lan": {
                "baseUrl": "http://192.0.2.10:8080/v1",
                "api": "openai-completions",
                "apiKey": LOCAL_AUTH_PLACEHOLDER,
                "models": [{"id": "Ornith"}],
            }
        }
    }


def test_verified_capabilities_and_env_auth_are_rendered_explicitly() -> None:
    manager = PiModelsConfigManager()
    payload = manager.build_payload(
        AgentSettings(
            provider="ornith-lan",
            model="Ornith",
            base_url="http://192.0.2.20:8080/v1",
            api="anthropic-messages",
            auth_mode="env",
            api_key_env="ORNITH_API_KEY",
            context_window=131_072,
            max_tokens=32_768,
            model_reasoning=True,
            model_supports_images=False,
            supports_developer_role=False,
            supports_reasoning_effort=False,
        )
    )

    provider = payload["providers"]["ornith-lan"]
    assert provider["apiKey"] == "$ORNITH_API_KEY"
    assert provider["compat"] == {
        "supportsDeveloperRole": False,
        "supportsReasoningEffort": False,
    }
    assert provider["models"] == [
        {
            "id": "Ornith",
            "reasoning": True,
            "input": ["text"],
            "contextWindow": 131_072,
            "maxTokens": 32_768,
        }
    ]


def test_image_capability_is_only_added_when_verified() -> None:
    payload = PiModelsConfigManager().build_payload(
        AgentSettings(
            provider="local",
            model="multimodal-model",
            base_url="http://192.0.2.30:8080/v1",
            model_supports_images=True,
        )
    )

    assert payload["providers"]["local"]["models"][0]["input"] == [
        "text",
        "image",
    ]


def test_incomplete_profile_is_rejected_before_file_write(tmp_path: Path) -> None:
    manager = PiModelsConfigManager()
    paths = PiRuntimePaths.for_workspace(tmp_path)

    with pytest.raises(ModelConfigError, match="provider, model, base_url"):
        manager.write(AgentSettings(), paths)

    assert not (tmp_path / ".pi-agent/models.json").exists()


def test_authenticated_profile_requires_environment_variable_name() -> None:
    manager = PiModelsConfigManager()
    with pytest.raises(ModelConfigError, match="requires api_key_env"):
        manager.build_payload(
            AgentSettings(
                provider="local",
                model="model",
                base_url="http://192.0.2.40:8080/v1",
                auth_mode="env",
                api_key_env=None,
            )
        )


def test_models_config_is_written_atomically_without_secret_value(tmp_path: Path) -> None:
    manager = PiModelsConfigManager()
    paths = PiRuntimePaths.for_workspace(tmp_path)
    settings = AgentSettings(
        provider="ornith-lan",
        model="Ornith",
        base_url="http://192.0.2.50:8080/v1",
        auth_mode="env",
        api_key_env="ORNITH_API_KEY",
    )

    result = manager.write(settings, paths)
    raw = result.path.read_text(encoding="utf-8")
    parsed = json.loads(raw)

    assert result.path == tmp_path.resolve() / ".pi-agent/models.json"
    assert parsed["providers"]["ornith-lan"]["apiKey"] == "$ORNITH_API_KEY"
    assert "actual-secret-value" not in raw
    assert not list(result.path.parent.glob("*.tmp"))
    if os.name == "posix":
        assert result.path.stat().st_mode & 0o777 == 0o600
