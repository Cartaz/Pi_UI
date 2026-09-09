from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from core.settings import (
    AgentSettings,
    AppSettings,
    SettingsStore,
    SettingsValidationError,
    default_config_dir,
    default_data_dir,
    default_state_dir,
)


def test_xdg_paths_are_respected() -> None:
    env = {
        "HOME": "/home/tester",
        "XDG_CONFIG_HOME": "/cfg",
        "XDG_DATA_HOME": "/data",
        "XDG_STATE_HOME": "/state",
    }
    assert default_config_dir(env) == Path("/cfg/pi-ui")
    assert default_data_dir(env) == Path("/data/pi-ui")
    assert default_state_dir(env) == Path("/state/pi-ui")


def test_missing_settings_returns_defaults(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    assert store.load() == AppSettings()
    assert store.last_recovery is None


def test_round_trip_settings_endpoint_and_session_change(tmp_path: Path) -> None:
    path = tmp_path / "config" / "settings.json"
    store = SettingsStore(path)
    settings = AppSettings(
        workspace_root="/home/tester/Knowledge",
        last_session_id="01abc-session_1",
        agent=AgentSettings(
            provider="ornith-lan",
            model="ornith-1.5",
            base_url="http://192.0.2.10:8080/v1",
            context_window=131072,
            max_tokens=16384,
        ),
    )

    store.save(settings)
    loaded = store.load()
    assert loaded == settings

    changed = replace(
        loaded,
        last_session_id="01abc-session_2",
        agent=replace(loaded.agent, base_url="http://192.0.2.11:8080/v1"),
    )
    store.save(changed)
    reloaded = store.load()
    assert reloaded.agent.base_url == "http://192.0.2.11:8080/v1"
    assert reloaded.last_session_id == "01abc-session_2"


def test_schema_four_migrates_without_inventing_session_id(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 4,
                "workspace_root": "/home/tester/Knowledge",
                "agent": {},
            }
        ),
        encoding="utf-8",
    )

    loaded = SettingsStore(path).load()

    assert loaded.schema_version == 5
    assert loaded.workspace_root == "/home/tester/Knowledge"
    assert loaded.last_session_id is None


def test_save_leaves_no_temporary_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    store.save(AppSettings())
    assert [item.name for item in tmp_path.iterdir()] == ["settings.json"]


@pytest.mark.parametrize(
    "payload",
    [
        "{broken",
        json.dumps({"schema_version": 1, "surprise": True}),
        json.dumps({"schema_version": 1, "agent": {"context_window": -1}}),
        json.dumps({"schema_version": 99}),
    ],
)
def test_invalid_settings_are_preserved_and_defaults_are_recovered(
    tmp_path: Path, payload: str
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(payload, encoding="utf-8")
    store = SettingsStore(path)

    assert store.load() == AppSettings()
    assert not path.exists()
    assert store.last_recovery is not None
    assert store.last_recovery.quarantined_path.read_text(encoding="utf-8") == payload


def test_rejects_credentials_embedded_in_base_url_on_save(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    settings = AppSettings(
        agent=AgentSettings(base_url="http://secret@example.invalid/v1")
    )
    with pytest.raises(SettingsValidationError, match="must not contain credentials"):
        store.save(settings)


@pytest.mark.parametrize("session_id", ["", "bad/session", "-bad", "bad-", "bad space"])
def test_rejects_invalid_persisted_session_id(tmp_path: Path, session_id: str) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    with pytest.raises(SettingsValidationError, match="last_session_id"):
        store.save(AppSettings(last_session_id=session_id))
