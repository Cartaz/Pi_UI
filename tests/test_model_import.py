from __future__ import annotations

from core.agent.model_discovery import DiscoveredModelProfile, ExistingAuthKind
from core.agent.model_import import ModelImportBlocker, PiModelImportService
from core.settings import AgentSettings


def test_keyless_discovered_profile_proposes_import_without_guessing() -> None:
    profile = DiscoveredModelProfile(
        provider="ornith-lan",
        model="Ornith",
        base_url="http://192.0.2.80:8080/v1",
        api="openai-completions",
        auth_kind=ExistingAuthKind.KEYLESS_PLACEHOLDER,
        api_key_env=None,
        context_window=131072,
        max_tokens=32768,
        reasoning=True,
        supports_images=False,
        supports_developer_role=False,
        supports_reasoning_effort=False,
    )

    proposal = PiModelImportService().propose(profile)

    assert proposal.ready is True
    assert proposal.blockers == ()
    assert proposal.settings is not None
    assert proposal.settings.provider == "ornith-lan"
    assert proposal.settings.model == "Ornith"
    assert proposal.settings.base_url == "http://192.0.2.80:8080/v1"
    assert proposal.settings.auth_mode == "none"
    assert proposal.settings.api_key_env is None
    assert proposal.settings.context_window == 131072
    assert proposal.settings.max_tokens == 32768
    assert proposal.settings.model_reasoning is True
    assert proposal.settings.model_supports_images is False


def test_env_auth_profile_preserves_only_environment_reference() -> None:
    profile = _profile(
        auth_kind=ExistingAuthKind.ENV,
        api_key_env="ORNITH_API_KEY",
    )

    proposal = PiModelImportService().propose(profile)

    assert proposal.ready is True
    assert proposal.settings is not None
    assert proposal.settings.auth_mode == "env"
    assert proposal.settings.api_key_env == "ORNITH_API_KEY"


def test_literal_or_external_auth_blocks_automatic_import() -> None:
    proposal = PiModelImportService().propose(
        _profile(auth_kind=ExistingAuthKind.OTHER, api_key_env=None)
    )

    assert proposal.ready is False
    assert proposal.settings is None
    assert proposal.blockers == (ModelImportBlocker.AUTH_NOT_PORTABLE,)


def test_missing_auth_configuration_blocks_automatic_import() -> None:
    proposal = PiModelImportService().propose(
        _profile(auth_kind=ExistingAuthKind.MISSING, api_key_env=None)
    )

    assert proposal.ready is False
    assert proposal.blockers == (ModelImportBlocker.AUTH_NOT_PORTABLE,)


def test_missing_endpoint_and_unsupported_api_report_all_blockers() -> None:
    profile = _profile(
        base_url=None,
        api="custom-unsupported-api",
        auth_kind=ExistingAuthKind.KEYLESS_PLACEHOLDER,
        api_key_env=None,
    )

    proposal = PiModelImportService().propose(profile)

    assert proposal.ready is False
    assert proposal.settings is None
    assert proposal.blockers == (
        ModelImportBlocker.MISSING_BASE_URL,
        ModelImportBlocker.UNSUPPORTED_API,
    )


def test_runtime_policy_is_preserved_from_current_settings() -> None:
    current = AgentSettings(
        executable="/custom/runtime/bin/pi",
        runtime_root="/custom/runtime",
        bubblewrap_executable="/custom/bwrap",
        sandbox_enabled=False,
        startup_timeout_ms=12345,
        shutdown_timeout_ms=6789,
        thinking_level="high",
    )

    proposal = PiModelImportService().propose(
        _profile(
            auth_kind=ExistingAuthKind.KEYLESS_PLACEHOLDER,
            api_key_env=None,
        ),
        current=current,
    )

    assert proposal.ready is True
    assert proposal.settings is not None
    assert proposal.settings.executable == "/custom/runtime/bin/pi"
    assert proposal.settings.runtime_root == "/custom/runtime"
    assert proposal.settings.bubblewrap_executable == "/custom/bwrap"
    assert proposal.settings.sandbox_enabled is False
    assert proposal.settings.startup_timeout_ms == 12345
    assert proposal.settings.shutdown_timeout_ms == 6789
    assert proposal.settings.thinking_level == "high"


def _profile(
    *,
    base_url: str | None = "http://192.0.2.81:8080/v1",
    api: str | None = "openai-completions",
    auth_kind: ExistingAuthKind,
    api_key_env: str | None,
) -> DiscoveredModelProfile:
    return DiscoveredModelProfile(
        provider="ornith-lan",
        model="Ornith",
        base_url=base_url,
        api=api,
        auth_kind=auth_kind,
        api_key_env=api_key_env,
        context_window=None,
        max_tokens=None,
        reasoning=None,
        supports_images=None,
        supports_developer_role=None,
        supports_reasoning_effort=None,
    )
