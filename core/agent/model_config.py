"""Generate Pi ``models.json`` from canonical Pi_UI settings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from core.atomic_file import atomic_write_text
from core.settings import AgentSettings

from .runtime import PiRuntimePaths

LOCAL_AUTH_PLACEHOLDER: Final = "pi-ui-local"


class ModelConfigError(ValueError):
    """Raised when the configured model profile is not launch-ready."""


@dataclass(frozen=True, slots=True)
class ModelsConfigWriteResult:
    path: Path
    provider: str
    model: str


class PiModelsConfigManager:
    """Own the derived Pi custom-model file inside the AIOS runtime area.

    ``models.json`` is not a second source of truth. It is generated from
    ``AgentSettings`` immediately before the managed Pi runtime needs it.
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
        atomic_write_text(target, payload, mode=0o600)
        assert settings.provider is not None
        assert settings.model is not None
        return ModelsConfigWriteResult(
            path=target,
            provider=settings.provider,
            model=settings.model,
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
