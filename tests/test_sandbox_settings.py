from __future__ import annotations

from pathlib import Path

import pytest

from core.settings import AgentSettings, AppSettings, SettingsStore, SettingsValidationError


def test_sandbox_executable_must_live_inside_runtime_root(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    settings = AppSettings(
        agent=AgentSettings(
            executable="/usr/bin/pi",
            runtime_root="/opt/pi-agent",
        )
    )

    with pytest.raises(SettingsValidationError, match="inside runtime_root"):
        store.save(settings)


def test_bubblewrap_path_must_be_absolute(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    settings = AppSettings(agent=AgentSettings(bubblewrap_executable="bwrap"))

    with pytest.raises(SettingsValidationError, match="absolute path"):
        store.save(settings)


def test_process_timeouts_must_be_positive(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    settings = AppSettings(agent=AgentSettings(startup_timeout_ms=0))

    with pytest.raises(SettingsValidationError, match="startup_timeout_ms"):
        store.save(settings)
