"""Prepare the canonical Pi runtime before QProcess starts it."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from core.settings import AgentSettings

from .model_config import ModelsConfigWriteResult, PiModelsConfigManager
from .runtime import (
    PiLaunchSpec,
    PiRuntimePaths,
    build_launch_spec,
    prepare_runtime_paths,
)


class PiRuntimeBootstrapError(RuntimeError):
    """Raised when the managed Pi runtime cannot be prepared safely."""


class MissingRuntimeCredentialError(PiRuntimeBootstrapError):
    """Raised before writes when a configured credential is unavailable."""


@dataclass(frozen=True, slots=True)
class PreparedPiRuntime:
    paths: PiRuntimePaths
    models_config: ModelsConfigWriteResult
    launch_spec: PiLaunchSpec


class PiRuntimeBootstrap:
    """Coordinate the small, ordered mutation required before launching Pi.

    The model file is derived from canonical settings, then the immutable
    QProcess launch specification is built from the same settings. No process
    is started here; Qt remains the lifecycle owner in ``ui/native``.
    """

    def __init__(
        self,
        model_config: PiModelsConfigManager | None = None,
    ) -> None:
        self._model_config = model_config or PiModelsConfigManager()

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
