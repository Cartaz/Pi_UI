"""Typed application settings with XDG paths and atomic persistence."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Final
from urllib.parse import urlsplit

from core.atomic_file import atomic_write_text, fsync_directory

APP_DIR_NAME: Final = "pi-ui"
CURRENT_SCHEMA_VERSION: Final = 3
SUPPORTED_MODEL_APIS: Final = frozenset(
    {
        "openai-completions",
        "openai-responses",
        "anthropic-messages",
        "google-generative-ai",
    }
)
_ENV_NAME_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SettingsError(RuntimeError):
    """Base class for settings failures."""


class SettingsValidationError(SettingsError):
    """Raised when a settings payload violates the supported schema."""


@dataclass(frozen=True, slots=True)
class SettingsRecovery:
    """Describes a malformed settings file preserved during recovery."""

    quarantined_path: Path
    reason: str


@dataclass(frozen=True, slots=True)
class AgentSettings:
    """Pi runtime and model configuration owned by Pi_UI.

    Secrets are deliberately not stored here. ``api_key_env`` names an
    environment variable copied into the sanitized Pi process environment.
    Model capabilities use ``None`` when the baseline has not been verified;
    the derived Pi config then omits the corresponding field instead of
    inventing a capability.
    """

    executable: str = "/opt/pi-agent/bin/pi"
    runtime_root: str = "/opt/pi-agent"
    sandbox_enabled: bool = True
    bubblewrap_executable: str = "/usr/bin/bwrap"
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api: str = "openai-completions"
    auth_mode: str = "none"
    api_key_env: str | None = None
    context_window: int | None = None
    max_tokens: int | None = None
    model_reasoning: bool | None = None
    model_supports_images: bool | None = None
    supports_developer_role: bool | None = None
    supports_reasoning_effort: bool | None = None
    thinking_level: str | None = None
    skip_version_check: bool = True
    offline_startup: bool = False
    startup_timeout_ms: int = 10_000
    shutdown_timeout_ms: int = 5_000


@dataclass(frozen=True, slots=True)
class AppSettings:
    schema_version: int = CURRENT_SCHEMA_VERSION
    workspace_root: str | None = None
    agent: AgentSettings = field(default_factory=AgentSettings)


def default_config_dir(env: dict[str, str] | None = None) -> Path:
    values = os.environ if env is None else env
    xdg = values.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / APP_DIR_NAME
    return Path(values.get("HOME", str(Path.home()))) / ".config" / APP_DIR_NAME


def default_data_dir(env: dict[str, str] | None = None) -> Path:
    values = os.environ if env is None else env
    xdg = values.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / APP_DIR_NAME
    return Path(values.get("HOME", str(Path.home()))) / ".local" / "share" / APP_DIR_NAME


def default_state_dir(env: dict[str, str] | None = None) -> Path:
    values = os.environ if env is None else env
    xdg = values.get("XDG_STATE_HOME")
    if xdg:
        return Path(xdg) / APP_DIR_NAME
    return Path(values.get("HOME", str(Path.home()))) / ".local" / "state" / APP_DIR_NAME


class SettingsStore:
    """Single owner for Pi_UI's persisted application settings."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (default_config_dir() / "settings.json")
        self.last_recovery: SettingsRecovery | None = None

    def load(self) -> AppSettings:
        self.last_recovery = None
        if not self.path.exists():
            return AppSettings()

        try:
            text = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise SettingsError(f"cannot read settings from {self.path}") from exc

        try:
            raw = json.loads(text)
            return _parse_settings(_migrate_settings(raw))
        except (json.JSONDecodeError, SettingsValidationError) as exc:
            quarantined = self._quarantine_invalid_file()
            self.last_recovery = SettingsRecovery(
                quarantined_path=quarantined,
                reason=str(exc),
            )
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        validated = _parse_settings(_migrate_settings(asdict(settings)))
        payload = json.dumps(
            asdict(validated),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n"
        atomic_write_text(self.path, payload)

    def _quarantine_invalid_file(self) -> Path:
        suffix = f".invalid-{time.time_ns()}"
        quarantined = self.path.with_name(self.path.name + suffix)
        try:
            os.replace(self.path, quarantined)
            fsync_directory(self.path.parent)
        except OSError as exc:
            raise SettingsError(
                f"settings are invalid and could not be preserved: {self.path}"
            ) from exc
        return quarantined


def _migrate_settings(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SettingsValidationError("settings root must be a JSON object")

    version = raw.get("schema_version", 1)
    if version == CURRENT_SCHEMA_VERSION:
        return dict(raw)
    if version not in {1, 2}:
        raise SettingsValidationError(
            f"unsupported settings schema version: {version!r}"
        )

    migrated = dict(raw)
    agent_raw = migrated.get("agent", {})
    if not isinstance(agent_raw, dict):
        raise SettingsValidationError("agent settings must be a JSON object")
    agent = dict(agent_raw)

    if version == 1 and agent.get("executable", "pi") == "pi":
        agent["executable"] = AgentSettings().executable

    # Schema 3 makes server authentication explicit. Existing configurations
    # that already named an API-key environment variable preserve that intent.
    agent.setdefault("auth_mode", "env" if agent.get("api_key_env") else "none")

    migrated["agent"] = agent
    migrated["schema_version"] = CURRENT_SCHEMA_VERSION
    return migrated


def _parse_settings(raw: Any) -> AppSettings:
    if not isinstance(raw, dict):
        raise SettingsValidationError("settings root must be a JSON object")

    allowed_root = {"schema_version", "workspace_root", "agent"}
    unknown_root = set(raw) - allowed_root
    if unknown_root:
        raise SettingsValidationError(
            f"unknown settings keys: {', '.join(sorted(unknown_root))}"
        )

    schema_version = raw.get("schema_version", CURRENT_SCHEMA_VERSION)
    if schema_version != CURRENT_SCHEMA_VERSION:
        raise SettingsValidationError(
            f"unsupported settings schema version: {schema_version!r}"
        )

    workspace_root = raw.get("workspace_root")
    if workspace_root is not None:
        if not isinstance(workspace_root, str) or not workspace_root.strip():
            raise SettingsValidationError(
                "workspace_root must be a non-empty string or null"
            )

    agent_raw = raw.get("agent", {})
    if not isinstance(agent_raw, dict):
        raise SettingsValidationError("agent settings must be a JSON object")

    agent = _parse_agent_settings(agent_raw)
    return AppSettings(
        schema_version=CURRENT_SCHEMA_VERSION,
        workspace_root=workspace_root,
        agent=agent,
    )


def _parse_agent_settings(raw: dict[str, Any]) -> AgentSettings:
    defaults = AgentSettings()
    allowed = set(asdict(defaults))
    unknown = set(raw) - allowed
    if unknown:
        raise SettingsValidationError(
            f"unknown agent settings keys: {', '.join(sorted(unknown))}"
        )

    values = asdict(defaults)
    values.update(raw)

    for key in ("executable", "runtime_root", "bubblewrap_executable", "api"):
        _require_non_empty_string(values, key)
    for key in ("provider", "model", "base_url", "api_key_env", "thinking_level"):
        _optional_non_empty_string(values, key)

    if values["api"] not in SUPPORTED_MODEL_APIS:
        raise SettingsValidationError(f"unsupported Pi model API: {values['api']}")
    if values["auth_mode"] not in {"none", "env"}:
        raise SettingsValidationError("auth_mode must be 'none' or 'env'")

    if values["base_url"] is not None:
        _validate_base_url(values["base_url"])
    if values["api_key_env"] is not None and not _ENV_NAME_RE.fullmatch(
        values["api_key_env"]
    ):
        raise SettingsValidationError("api_key_env must be an environment variable name")
    if values["auth_mode"] == "env" and values["api_key_env"] is None:
        raise SettingsValidationError(
            "api_key_env is required when auth_mode is 'env'"
        )

    for key in ("context_window", "max_tokens"):
        value = values[key]
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
        ):
            raise SettingsValidationError(f"{key} must be a positive integer or null")

    for key in ("startup_timeout_ms", "shutdown_timeout_ms"):
        value = values[key]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise SettingsValidationError(f"{key} must be a positive integer")

    for key in ("sandbox_enabled", "skip_version_check", "offline_startup"):
        if not isinstance(values[key], bool):
            raise SettingsValidationError(f"{key} must be a boolean")

    for key in (
        "model_reasoning",
        "model_supports_images",
        "supports_developer_role",
        "supports_reasoning_effort",
    ):
        value = values[key]
        if value is not None and not isinstance(value, bool):
            raise SettingsValidationError(f"{key} must be a boolean or null")

    if values["sandbox_enabled"]:
        executable = PurePosixPath(values["executable"])
        runtime_root = PurePosixPath(values["runtime_root"])
        bubblewrap = PurePosixPath(values["bubblewrap_executable"])
        if not executable.is_absolute() or not runtime_root.is_absolute():
            raise SettingsValidationError(
                "sandboxed executable and runtime_root must be absolute paths"
            )
        if not bubblewrap.is_absolute():
            raise SettingsValidationError(
                "bubblewrap_executable must be an absolute path when sandboxing"
            )
        try:
            executable.relative_to(runtime_root)
        except ValueError as exc:
            raise SettingsValidationError(
                "sandboxed executable must be inside runtime_root"
            ) from exc

    return AgentSettings(**values)


def _validate_base_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SettingsValidationError("base_url must be an absolute http(s) URL")
    if parsed.username is not None or parsed.password is not None:
        raise SettingsValidationError("base_url must not contain credentials")


def _require_non_empty_string(values: dict[str, Any], key: str) -> None:
    value = values[key]
    if not isinstance(value, str) or not value.strip():
        raise SettingsValidationError(f"{key} must be a non-empty string")


def _optional_non_empty_string(values: dict[str, Any], key: str) -> None:
    value = values[key]
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise SettingsValidationError(f"{key} must be a non-empty string or null")
