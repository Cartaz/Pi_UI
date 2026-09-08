"""Read-only discovery of an existing Pi ``models.json`` baseline."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .model_config import LOCAL_AUTH_PLACEHOLDER, MANAGED_MARKER_FILENAME, ModelConfigError
from .runtime import PiRuntimePaths

_ENV_REFERENCE_RE = re.compile(r"^\$(?:([A-Za-z_][A-Za-z0-9_]*)|\{([A-Za-z_][A-Za-z0-9_]*)\})$")


class ExistingAuthKind(StrEnum):
    MISSING = "missing"
    KEYLESS_PLACEHOLDER = "keyless-placeholder"
    ENV = "env"
    OTHER = "other"


class ModelConfigManagementState(StrEnum):
    MISSING = "missing"
    UNMANAGED = "unmanaged"
    MANAGED = "managed"
    CHANGED_EXTERNALLY = "changed-externally"


@dataclass(frozen=True, slots=True)
class DiscoveredModelProfile:
    provider: str
    model: str
    base_url: str | None
    api: str | None
    auth_kind: ExistingAuthKind
    api_key_env: str | None
    context_window: int | None
    max_tokens: int | None
    reasoning: bool | None
    supports_images: bool | None
    supports_developer_role: bool | None
    supports_reasoning_effort: bool | None


@dataclass(frozen=True, slots=True)
class ExistingModelsConfig:
    path: Path
    sha256: str | None
    management_state: ModelConfigManagementState
    profiles: tuple[DiscoveredModelProfile, ...]


class PiModelsConfigDiscovery:
    """Inspect the current runtime config without returning literal credentials."""

    def inspect(self, paths: PiRuntimePaths) -> ExistingModelsConfig:
        target = paths.host_agent_dir / "models.json"
        marker = paths.host_agent_dir / MANAGED_MARKER_FILENAME
        if not target.exists():
            return ExistingModelsConfig(
                path=target,
                sha256=None,
                management_state=(
                    ModelConfigManagementState.CHANGED_EXTERNALLY
                    if marker.exists()
                    else ModelConfigManagementState.MISSING
                ),
                profiles=(),
            )

        try:
            raw_bytes = target.read_bytes()
            raw = json.loads(raw_bytes.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ModelConfigError(f"existing Pi models config is invalid: {target}") from exc
        if not isinstance(raw, dict):
            raise ModelConfigError("existing Pi models config root must be an object")

        digest = hashlib.sha256(raw_bytes).hexdigest()
        profiles = tuple(self._profiles(raw))
        return ExistingModelsConfig(
            path=target,
            sha256=digest,
            management_state=self._management_state(target, marker, digest),
            profiles=profiles,
        )

    def _profiles(self, raw: dict[str, Any]) -> list[DiscoveredModelProfile]:
        providers = raw.get("providers")
        if not isinstance(providers, dict):
            return []

        result: list[DiscoveredModelProfile] = []
        for provider_name, provider_raw in providers.items():
            if not isinstance(provider_name, str) or not isinstance(provider_raw, dict):
                continue

            base_url = _optional_string(provider_raw.get("baseUrl"))
            provider_api = _optional_string(provider_raw.get("api"))
            auth_kind, api_key_env = _classify_auth(provider_raw.get("apiKey"))
            provider_compat = _compat_flags(provider_raw.get("compat"))
            models = provider_raw.get("models")
            if not isinstance(models, list):
                continue

            for model_raw in models:
                if not isinstance(model_raw, dict):
                    continue
                model_id = _optional_string(model_raw.get("id"))
                if not model_id:
                    continue

                model_compat = dict(provider_compat)
                model_compat.update(_compat_flags(model_raw.get("compat")))
                result.append(
                    DiscoveredModelProfile(
                        provider=provider_name,
                        model=model_id,
                        base_url=base_url,
                        api=_optional_string(model_raw.get("api")) or provider_api,
                        auth_kind=auth_kind,
                        api_key_env=api_key_env,
                        context_window=_positive_int(model_raw.get("contextWindow")),
                        max_tokens=_positive_int(model_raw.get("maxTokens")),
                        reasoning=_optional_bool(model_raw.get("reasoning")),
                        supports_images=_supports_images(model_raw.get("input")),
                        supports_developer_role=model_compat.get("supportsDeveloperRole"),
                        supports_reasoning_effort=model_compat.get("supportsReasoningEffort"),
                    )
                )
        return result

    @staticmethod
    def _management_state(
        target: Path,
        marker: Path,
        actual_hash: str,
    ) -> ModelConfigManagementState:
        if not marker.exists():
            return ModelConfigManagementState.UNMANAGED
        try:
            marker_raw = json.loads(marker.read_text(encoding="utf-8"))
            expected_hash = marker_raw.get("sha256") if isinstance(marker_raw, dict) else None
            if (
                not isinstance(marker_raw, dict)
                or marker_raw.get("schema") != 1
                or marker_raw.get("managedBy") != "Pi_UI"
                or not isinstance(expected_hash, str)
            ):
                return ModelConfigManagementState.CHANGED_EXTERNALLY
        except (OSError, UnicodeError, json.JSONDecodeError):
            return ModelConfigManagementState.CHANGED_EXTERNALLY
        return (
            ModelConfigManagementState.MANAGED
            if actual_hash == expected_hash
            else ModelConfigManagementState.CHANGED_EXTERNALLY
        )


def _classify_auth(value: object) -> tuple[ExistingAuthKind, str | None]:
    if value is None:
        return ExistingAuthKind.MISSING, None
    if value == LOCAL_AUTH_PLACEHOLDER:
        return ExistingAuthKind.KEYLESS_PLACEHOLDER, None
    if isinstance(value, str):
        match = _ENV_REFERENCE_RE.fullmatch(value)
        if match:
            return ExistingAuthKind.ENV, match.group(1) or match.group(2)
    return ExistingAuthKind.OTHER, None


def _compat_flags(value: object) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, bool] = {}
    for key in ("supportsDeveloperRole", "supportsReasoningEffort"):
        item = value.get(key)
        if isinstance(item, bool):
            result[key] = item
    return result


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _positive_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _supports_images(value: object) -> bool | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    if "image" in value:
        return True
    if "text" in value:
        return False
    return None
