from __future__ import annotations

import json
from pathlib import Path

from core.agent.model_discovery import (
    DiscoveredModelProfile,
    ExistingAuthKind,
    ExistingModelsConfig,
    ModelConfigManagementState,
)
from core.preflight import (
    CommandProbe,
    CommandProbeResult,
    HostRuntimeFacts,
    PreflightCheck,
    PreflightPlanner,
    PreflightStatus,
    classify_probe_result,
    sanitized_manifest_json,
)
from core.settings import AgentSettings


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _facts(node: Path | None) -> HostRuntimeFacts:
    return HostRuntimeFacts(
        os_name="Linux",
        os_release="test-kernel",
        python_version="3.13.0",
        pyside_version="6.11.2",
        qt_version="6.11.2",
        node_executable=str(node) if node else None,
    )


def _profile() -> DiscoveredModelProfile:
    return DiscoveredModelProfile(
        provider="ornith-lan",
        model="Ornith",
        base_url="http://192.0.2.40:8080/v1",
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


def test_linux_plan_discovers_host_probes_without_mutating_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "AIOS"
    workspace.mkdir()
    runtime_root = tmp_path / "runtime"
    pi = _make_executable(runtime_root / "bin" / "pi")
    bwrap = _make_executable(tmp_path / "bin" / "bwrap")
    node = _make_executable(tmp_path / "bin" / "node")
    models_path = workspace / ".pi-agent" / "models.json"
    existing = ExistingModelsConfig(
        path=models_path,
        sha256="abc",
        management_state=ModelConfigManagementState.UNMANAGED,
        profiles=(_profile(),),
    )

    settings = AgentSettings(
        executable=str(pi),
        runtime_root=str(runtime_root),
        bubblewrap_executable=str(bwrap),
    )
    plan = PreflightPlanner().build(
        settings,
        workspace=workspace,
        existing_models=existing,
        facts=_facts(node),
    )

    checks = {item.check_id: item for item in plan.checks}
    assert checks["host-os"].status == PreflightStatus.PASS
    assert checks["workspace"].status == PreflightStatus.PASS
    assert checks["sandbox-enabled"].status == PreflightStatus.PASS
    assert checks["models-config"].status == PreflightStatus.PASS
    assert checks["network-policy"].status == PreflightStatus.WARN
    assert checks["confinement-runtime"].status == PreflightStatus.PENDING
    assert {probe.probe_id for probe in plan.probes} == {"bubblewrap", "pi", "node"}
    assert dict(plan.environment)["PI_OFFLINE"] == "1"
    assert dict(plan.environment)["PI_SKIP_VERSION_CHECK"] == "1"
    assert not (workspace / ".pi-agent").exists()


def test_missing_workspace_and_disabled_sandbox_are_blocking(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    pi = _make_executable(runtime_root / "bin" / "pi")
    node = _make_executable(tmp_path / "node")
    settings = AgentSettings(
        executable=str(pi),
        runtime_root=str(runtime_root),
        sandbox_enabled=False,
        bubblewrap_executable=str(tmp_path / "missing-bwrap"),
    )

    plan = PreflightPlanner().build(
        settings,
        workspace=None,
        existing_models=None,
        facts=_facts(node),
    )
    checks = {item.check_id: item for item in plan.checks}

    assert checks["workspace"].status == PreflightStatus.FAIL
    assert checks["sandbox-enabled"].status == PreflightStatus.FAIL
    assert checks["bubblewrap"].status == PreflightStatus.WARN
    assert checks["models-config"].status == PreflightStatus.FAIL


def test_changed_managed_models_file_is_warning_not_silent_adoption(tmp_path: Path) -> None:
    existing = ExistingModelsConfig(
        path=tmp_path / "models.json",
        sha256="abc",
        management_state=ModelConfigManagementState.CHANGED_EXTERNALLY,
        profiles=(_profile(),),
    )

    check = PreflightPlanner._models_check(existing)

    assert check.status == PreflightStatus.WARN
    assert "fingerprint changed" in check.summary
    assert "not overwrite" in check.detail


def test_probe_result_classification_preserves_required_semantics() -> None:
    required = CommandProbe("pi", "Pi", "/opt/pi/bin/pi", ("--version",), required=True)
    optional = CommandProbe("bwrap", "Bubblewrap", "/usr/bin/bwrap", ("--version",), required=False)

    success = classify_probe_result(
        required,
        CommandProbeResult("pi", 0, "pi 1.2.3\n", ""),
    )
    timeout = classify_probe_result(
        required,
        CommandProbeResult("pi", None, "", "", timed_out=True),
    )
    missing_optional = classify_probe_result(
        optional,
        CommandProbeResult("bwrap", None, "", "", start_error="not found"),
    )

    assert success.status == PreflightStatus.PASS
    assert success.summary == "pi 1.2.3"
    assert timeout.status == PreflightStatus.FAIL
    assert missing_optional.status == PreflightStatus.WARN


def test_manifest_redacts_local_paths(tmp_path: Path) -> None:
    secret_path = str(tmp_path / "private" / "runtime")
    checks = (
        PreflightCheck("pi", "Pi", PreflightStatus.PASS, "pi 1.2.3", secret_path),
        PreflightCheck(
            "workspace",
            "Workspace",
            PreflightStatus.PASS,
            "Workspace directory is available",
            str(tmp_path / "AIOS"),
        ),
        PreflightCheck(
            "network-policy",
            "Network",
            PreflightStatus.WARN,
            "Host network shared",
            "No destination filtering",
        ),
    )

    text = sanitized_manifest_json(checks, _facts(None))
    payload = json.loads(text)

    assert secret_path not in text
    assert str(tmp_path / "AIOS") not in text
    assert payload["checks"][0]["detail"] == "<local-path>"
    assert payload["checks"][1]["detail"] == "<local-path>"
    assert payload["checks"][2]["detail"] == "No destination filtering"
