"""Generate Pi ``models.json`` from canonical Pi_UI settings."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from core.atomic_file import atomic_write_text
from core.settings import AgentSettings

from .runtime import PiRuntimePaths

LOCAL_AUTH_PLACEHOLDER: Final = "pi-ui-local"
MANAGED_MARKER_FILENAME: Final = ".models.json.pi-ui-managed"
_MANAGED_MARKER_SCHEMA: Final = 1


class ModelConfigError(ValueError):
    """Raised when the configured model profile is not launch-ready."""


class UnmanagedModelsConfigError(ModelConfigError):
    """Raised instead of overwriting a models.json not owned by Pi_UI."""


class ModelsConfigChangedExternallyError(ModelConfigError):
    """Raised when a managed models.json changed outside Pi_UI."""


@dataclass(frozen=True, slots=True)
class ModelsConfigWriteResult:
    path: Path
    provider: str
    model: str


class PiModelsConfigManager:
    """Own the derived Pi custom-model file inside the AIOS runtime area.

    ``models.json`` is not a second source of truth. It is generated from
    ``AgentSettings`` immediately before the managed Pi runtime needs it.
    Pre-existing files are never adopted implicitly, and external edits to a
    previously managed file are detected by a content hash before replacement.
    """

    def build_payload(self, settings: AgentSettings) -> dict[str, Any]:
        missing = tuple(
            name
            for name, value in (
                ("provider", settings.provider),
                ("model", settings.model),
                ("base_url", settings.base_url),
            )
            if value is None
        )
        if missing:
            raise ModelConfigError(
                "model configuration is incomplete: " + ", ".join(missing)
            )

        assert settings.provider is not None
        assert settings.model is not None
        assert settings.base_url is not None

        provider: dict[str, Any] = {
            "baseUrl": settings.base_url,
            "api": settings.api,
            "apiKey": self._api_key_reference(settings),
        }

        compat = self._compat(settings)
        if compat:
            provider["compat"] = compat

        model: dict[str, Any] = {"id": settings.model}
        if settings.model_reasoning is not None:
            model["reasoning"] = settings.model_reasoning
        if settings.model_supports_images is not None:
            model["input"] = (
                ["text", "image"]
                if settings.model_supports_images
                else ["text"]
            )
        if settings.context_window is not None:
            model["contextWindow"] = settings.context_window
        if settings.max_tokens is not None:
            model["maxTokens"] = settings.max_tokens

        provider["models"] = [model]
        return {"providers": {settings.provider: provider}}

    def render(self, settings: AgentSettings) -> str:
        return json.dumps(
            self.build_payload(settings),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n"

    def write(
        self,
        settings: AgentSettings,
        paths: PiRuntimePaths,
    ) -> ModelsConfigWriteResult:
        payload = self.render(settings)
        target = paths.host_agent_dir / "models.json"
        marker = paths.host_agent_dir / MANAGED_MARKER_FILENAME
        self._assert_safe_to_replace(target, marker)

        atomic_write_text(target, payload, mode=0o600)
        marker_payload = json.dumps(
            {
                "schema": _MANAGED_MARKER_SCHEMA,
                "managedBy": "Pi_UI",
                "sha256": _sha256_text(payload),
            },
            indent=2,
            sort_keys=True,
        ) + "\n"
        atomic_write_text(marker, marker_payload, mode=0o600)

        assert settings.provider is not None
        assert settings.model is not None
        return ModelsConfigWriteResult(
            path=target,
            provider=settings.provider,
            model=settings.model,
        )

    def _assert_safe_to_replace(self, target: Path, marker: Path) -> None:
        target_exists = target.exists()
        marker_exists = marker.exists()

        if not target_exists and not marker_exists:
            return
        if target_exists and not marker_exists:
            raise UnmanagedModelsConfigError(
                f"refusing to overwrite unmanaged Pi model config: {target}"
            )
        if marker_exists and not target_exists:
            raise ModelsConfigChangedExternallyError(
                "Pi_UI model ownership marker exists but models.json is missing"
            )

        try:
            marker_data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ModelsConfigChangedExternallyError(
                "Pi_UI model ownership marker is unreadable or invalid"
            ) from exc

        expected_hash = marker_data.get("sha256") if isinstance(marker_data, dict) else None
        if (
            not isinstance(marker_data, dict)
            or marker_data.get("schema") != _MANAGED_MARKER_SCHEMA
            or marker_data.get("managedBy") != "Pi_UI"
            or not isinstance(expected_hash, str)
        ):
            raise ModelsConfigChangedExternallyError(
                "Pi_UI model ownership marker has an unsupported format"
            )

        try:
            actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        except OSError as exc:
            raise ModelsConfigChangedExternallyError(
                "managed models.json could not be read before replacement"
            ) from exc
        if actual_hash != expected_hash:
            raise ModelsConfigChangedExternallyError(
                "managed models.json changed outside Pi_UI; refusing to overwrite"
            )

    @staticmethod
    def _api_key_reference(settings: AgentSettings) -> str:
        if settings.auth_mode == "none":
            # Pi requires auth presence before a custom local model is exposed.
            # The literal is deliberately non-secret and is used only for a
            # server profile the user declared as not requiring auth.
            return LOCAL_AUTH_PLACEHOLDER
        if settings.auth_mode == "env" and settings.api_key_env:
            return f"${settings.api_key_env}"
        raise ModelConfigError("authenticated provider requires api_key_env")

    @staticmethod
    def _compat(settings: AgentSettings) -> dict[str, bool]:
        compat: dict[str, bool] = {}
        if settings.supports_developer_role is not None:
            compat["supportsDeveloperRole"] = settings.supports_developer_role
        if settings.supports_reasoning_effort is not None:
            compat["supportsReasoningEffort"] = settings.supports_reasoning_effort
        return compat


def _sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
