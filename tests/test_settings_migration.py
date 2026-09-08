from __future__ import annotations

import json
from pathlib import Path

from core.settings import CURRENT_SCHEMA_VERSION, SettingsStore


def test_schema_one_bare_pi_runtime_migrates_without_quarantine(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "workspace_root": "/home/tester/AI_OS",
                "agent": {
                    "executable": "pi",
                    "provider": "ornith-lan",
                    "model": "Ornith",
                },
            }
        ),
        encoding="utf-8",
    )
    store = SettingsStore(path)

    loaded = store.load()

    assert store.last_recovery is None
    assert loaded.schema_version == CURRENT_SCHEMA_VERSION
    assert loaded.workspace_root == "/home/tester/AI_OS"
    assert loaded.agent.executable == "/opt/pi-agent/bin/pi"
    assert loaded.agent.runtime_root == "/opt/pi-agent"
    assert loaded.agent.sandbox_enabled is True
    assert loaded.agent.provider == "ornith-lan"
    assert loaded.agent.model == "Ornith"
