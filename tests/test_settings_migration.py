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
    assert loaded.agent.auth_mode == "none"


def test_schema_two_api_key_env_migrates_to_explicit_env_auth(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "workspace_root": "/home/tester/AI_OS",
                "agent": {
                    "executable": "/opt/pi-agent/bin/pi",
                    "runtime_root": "/opt/pi-agent",
                    "sandbox_enabled": True,
                    "bubblewrap_executable": "/usr/bin/bwrap",
                    "provider": "ornith-lan",
                    "model": "Ornith",
                    "base_url": "http://192.0.2.10:8080/v1",
                    "api": "openai-completions",
                    "api_key_env": "ORNITH_API_KEY",
                    "context_window": None,
                    "max_tokens": None,
                    "thinking_level": None,
                    "skip_version_check": True,
                    "offline_startup": False,
                    "startup_timeout_ms": 10000,
                    "shutdown_timeout_ms": 5000,
                },
            }
        ),
        encoding="utf-8",
    )
    store = SettingsStore(path)

    loaded = store.load()

    assert store.last_recovery is None
    assert loaded.schema_version == CURRENT_SCHEMA_VERSION
    assert loaded.agent.auth_mode == "env"
    assert loaded.agent.api_key_env == "ORNITH_API_KEY"
    assert loaded.agent.model_reasoning is None
    assert loaded.agent.model_supports_images is None
