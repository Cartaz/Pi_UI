from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from core.settings import AgentSettings, AppSettings, SettingsStore, SettingsValidationError


def test_schema_three_migrates_timeout_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "workspace_root": None,
                "agent": {
                    "provider": "ornith-lan",
                    "model": "Ornith",
                    "base_url": "http://192.0.2.120:8080/v1",
                    "auth_mode": "none",
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = SettingsStore(path).load()

    assert loaded.schema_version == 6
    assert loaded.last_session_id is None
    assert loaded.agent.request_timeout_ms == 30_000
    assert loaded.agent.inactivity_timeout_ms == 180_000


def test_custom_timeout_values_round_trip(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    settings = AppSettings(
        agent=replace(
            AgentSettings(),
            request_timeout_ms=45_000,
            inactivity_timeout_ms=240_000,
        )
    )

    store.save(settings)

    assert store.load() == settings


@pytest.mark.parametrize("field", ["request_timeout_ms", "inactivity_timeout_ms"])
def test_timeout_values_must_be_positive(tmp_path: Path, field: str) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    agent = replace(AgentSettings(), **{field: 0})

    with pytest.raises(SettingsValidationError, match=field):
        store.save(AppSettings(agent=agent))
