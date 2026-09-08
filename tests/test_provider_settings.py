from __future__ import annotations

from pathlib import Path

import pytest

from core.settings import AgentSettings, AppSettings, SettingsStore, SettingsValidationError


def test_keyless_auth_rejects_unused_api_key_environment_reference(
    tmp_path: Path,
) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    settings = AppSettings(
        agent=AgentSettings(
            auth_mode="none",
            api_key_env="SHOULD_NOT_BE_EXPOSED",
        )
    )

    with pytest.raises(SettingsValidationError, match="must be null"):
        store.save(settings)


def test_env_auth_requires_api_key_environment_reference(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    settings = AppSettings(agent=AgentSettings(auth_mode="env"))

    with pytest.raises(SettingsValidationError, match="is required"):
        store.save(settings)


def test_unsupported_pi_model_api_is_rejected(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    settings = AppSettings(agent=AgentSettings(api="unknown-api"))

    with pytest.raises(SettingsValidationError, match="unsupported Pi model API"):
        store.save(settings)
