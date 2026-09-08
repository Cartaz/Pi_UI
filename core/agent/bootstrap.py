"""Prepare the Pi runtime before QProcess starts it."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Mapping

from core.settings import AgentSettings, SUPPORTED_MODEL_APIS

from .model_config import ModelsConfigWriteResult, PiModelsConfigManager
from .model_discovery import (
    DiscoveredModelProfile,
    ExistingAuthKind,
    ModelConfigManagementState,
    PiModelsConfigDiscovery,
)
from .runtime import (
    PiLaunchSpec,
    PiRuntimePaths,
    build_launch_spec,
    prepare_runtime_paths,
)


class PiRuntimeBootstrapError(RuntimeError):
    """Raised when the Pi runtime cannot be prepared safely."""


class MissingRuntimeCredentialError(PiRuntimeBootstrapError):
    """Raised before writes when a configured credential is unavailable."""


class ExistingRuntimeChangedError(PiRuntimeBootstrapError):
    """Raised when the selected existing models.json changed before launch."""


class ExistingRuntimeProfileError(PiRuntimeBootstrapError):
    """Raised when the selected model profile is no longer present."""


class RuntimeModelConfigSource(StrEnum):
    DERIVED = "derived"
    EXISTING = "existing"


@dataclass(frozen=True, slots=True)
class PreparedPiRuntime:
    paths: PiRuntimePaths
    models_config: ModelsConfigWriteResult | None
    launch_spec: PiLaunchSpec
    config_source: RuntimeModelConfigSource
    config_sha256: str | None = None


class PiRuntimeBootstrap:
    """Coordinate the ordered mutation required before launching Pi.

    ``prepare`` derives a Pi_UI-owned models.json from canonical settings.
    ``prepare_existing`` instead reuses a models.json already present in the
    AIOS root and never rewrites or adopts it. No process is started here; Qt
    remains the lifecycle owner in ``ui/native``.
    """

    def __init__(
        self,
        model_config: PiModelsConfigManager | None = None,
        discovery: PiModelsConfigDiscovery | None = None,
    ) -> None:
        self._model_config = model_config or PiModelsConfigManager()
        self._discovery = discovery or PiModelsConfigDiscovery()

    def prepare(
        self,
        settings: AgentSettings,
        *,
        workspace: Path,
        base_environment: Mapping[str, str] | None = None,
        user_name: str | None = None,
    ) -> PreparedPiRuntime:
        environment = dict(os.environ if base_environment is None else base_environment)
        self._validate_credential(settings, environment)

        paths = PiRuntimePaths.for_workspace(workspace)
        prepare_runtime_paths(paths)
        models_config = self._model_config.write(settings, paths)
        launch_spec = build_launch_spec(
            settings,
            working_directory=workspace,
            paths=paths,
            base_environment=environment,
            user_name=user_name,
        )
        return PreparedPiRuntime(
            paths=paths,
            models_config=models_config,
            launch_spec=launch_spec,
            config_source=RuntimeModelConfigSource.DERIVED,
        )

    def prepare_existing(
        self,
        settings: AgentSettings,
        *,
        workspace: Path,
        profile: DiscoveredModelProfile,
        expected_sha256: str,
        base_environment: Mapping[str, str] | None = None,
        user_name: str | None = None,
    ) -> PreparedPiRuntime:
        """Launch against an already-working models.json without modifying it."""

        environment = dict(os.environ if base_environment is None else base_environment)
        paths = PiRuntimePaths.for_workspace(workspace)
        existing = self._discovery.inspect(paths)

        if existing.sha256 != expected_sha256:
            raise ExistingRuntimeChangedError(
                "existing Pi models config changed after it was selected"
            )
        if existing.management_state == ModelConfigManagementState.CHANGED_EXTERNALLY:
            raise ExistingRuntimeChangedError(
                "existing Pi models config conflicts with its Pi_UI ownership marker"
            )
        if profile not in existing.profiles:
            raise ExistingRuntimeProfileError(
                f"selected Pi model profile is no longer present: "
                f"{profile.provider}/{profile.model}"
            )

        runtime_settings = self._settings_for_existing_profile(settings, profile)
        self._validate_credential(runtime_settings, environment)
        prepare_runtime_paths(paths)
        launch_spec = build_launch_spec(
            runtime_settings,
            working_directory=workspace,
            paths=paths,
            base_environment=environment,
            user_name=user_name,
        )
        return PreparedPiRuntime(
            paths=paths,
            models_config=None,
            launch_spec=launch_spec,
            config_source=RuntimeModelConfigSource.EXISTING,
            config_sha256=expected_sha256,
        )

    @staticmethod
    def _settings_for_existing_profile(
        settings: AgentSettings,
        profile: DiscoveredModelProfile,
    ) -> AgentSettings:
        auth_mode = "none"
        api_key_env: str | None = None
        if profile.auth_kind == ExistingAuthKind.ENV and profile.api_key_env:
            auth_mode = "env"
            api_key_env = profile.api_key_env

        api = settings.api
        if profile.api in SUPPORTED_MODEL_APIS:
            api = profile.api

        return replace(
            settings,
            provider=profile.provider,
            model=profile.model,
            base_url=profile.base_url,
            api=api,
            auth_mode=auth_mode,
            api_key_env=api_key_env,
            context_window=profile.context_window,
            max_tokens=profile.max_tokens,
            model_reasoning=profile.reasoning,
            model_supports_images=profile.supports_images,
            supports_developer_role=profile.supports_developer_role,
            supports_reasoning_effort=profile.supports_reasoning_effort,
        )

    @staticmethod
    def _validate_credential(
        settings: AgentSettings,
        environment: Mapping[str, str],
    ) -> None:
        if settings.auth_mode != "env":
            return
        if not settings.api_key_env:
            raise MissingRuntimeCredentialError(
                "authenticated provider has no api_key_env configured"
            )
        value = environment.get(settings.api_key_env)
        if not value:
            raise MissingRuntimeCredentialError(
                f"required environment variable is not set: {settings.api_key_env}"
            )
