"""Convert discovered Pi model profiles into explicit Pi_UI import proposals."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from core.settings import AgentSettings, SUPPORTED_MODEL_APIS

from .model_discovery import DiscoveredModelProfile, ExistingAuthKind


class ModelImportBlocker(StrEnum):
    MISSING_BASE_URL = "missing-base-url"
    MISSING_API = "missing-api"
    UNSUPPORTED_API = "unsupported-api"
    AUTH_NOT_PORTABLE = "auth-not-portable"


@dataclass(frozen=True, slots=True)
class PiModelImportProposal:
    """Read-only proposal for adopting one discovered model profile.

    ``settings`` is present only when the profile can be represented without
    guessing or exposing a credential. The caller must still explicitly save
    the proposed settings and adopt/replace any unmanaged ``models.json``.
    """

    provider: str
    model: str
    blockers: tuple[ModelImportBlocker, ...]
    settings: AgentSettings | None

    @property
    def ready(self) -> bool:
        return not self.blockers and self.settings is not None


class PiModelImportService:
    """Build safe settings proposals from read-only model discovery results."""

    def propose(
        self,
        profile: DiscoveredModelProfile,
        *,
        current: AgentSettings | None = None,
    ) -> PiModelImportProposal:
        blockers: list[ModelImportBlocker] = []

        if profile.base_url is None:
            blockers.append(ModelImportBlocker.MISSING_BASE_URL)

        if profile.api is None:
            blockers.append(ModelImportBlocker.MISSING_API)
        elif profile.api not in SUPPORTED_MODEL_APIS:
            blockers.append(ModelImportBlocker.UNSUPPORTED_API)

        auth_mode: str | None = None
        api_key_env: str | None = None
        if profile.auth_kind == ExistingAuthKind.KEYLESS_PLACEHOLDER:
            auth_mode = "none"
        elif profile.auth_kind == ExistingAuthKind.ENV and profile.api_key_env:
            auth_mode = "env"
            api_key_env = profile.api_key_env
        else:
            blockers.append(ModelImportBlocker.AUTH_NOT_PORTABLE)

        if blockers:
            return PiModelImportProposal(
                provider=profile.provider,
                model=profile.model,
                blockers=tuple(blockers),
                settings=None,
            )

        assert profile.base_url is not None
        assert profile.api is not None
        assert auth_mode is not None

        base = current or AgentSettings()
        proposed = replace(
            base,
            provider=profile.provider,
            model=profile.model,
            base_url=profile.base_url,
            api=profile.api,
            auth_mode=auth_mode,
            api_key_env=api_key_env,
            context_window=profile.context_window,
            max_tokens=profile.max_tokens,
            model_reasoning=profile.reasoning,
            model_supports_images=profile.supports_images,
            supports_developer_role=profile.supports_developer_role,
            supports_reasoning_effort=profile.supports_reasoning_effort,
        )
        return PiModelImportProposal(
            provider=profile.provider,
            model=profile.model,
            blockers=(),
            settings=proposed,
        )
