from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.preflight import CommandProbeResult, PreflightStatus
from core.sandbox_gate import SandboxGateError, SandboxGateService
from core.settings import AgentSettings

_CHECK_IDS = (
    "workspace-root",
    "workspace-write",
    "outside-direct",
    "symlink-escape",
    "child-inherits",
    "runtime-readonly",
    "usr-readonly",
    "synthetic-home",
    "desktop-env",
    "runtime-sockets",
    "pid-namespace",
)


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _settings(tmp_path: Path) -> tuple[AgentSettings, Path]:
    runtime_root = tmp_path / "runtime"
    pi = _make_executable(runtime_root / "bin" / "pi")
    node = _make_executable(runtime_root / "bin" / "node")
    bwrap = _make_executable(tmp_path / "bin" / "bwrap")
    settings = AgentSettings(
        executable=str(pi),
        runtime_root=str(runtime_root),
        bubblewrap_executable=str(bwrap),
    )
    return settings, node


def test_prepare_uses_canonical_policy_and_only_app_owned_scratch(tmp_path: Path) -> None:
    workspace = tmp_path / "AIOS"
    workspace.mkdir()
    outside_root = tmp_path / "state" / "sandbox-gates"
    settings, node = _settings(tmp_path)
    service = SandboxGateService(id_factory=lambda: "run-1")

    plan = service.prepare(
        settings,
        workspace=workspace,
        node_executable=str(node),
        outside_root=outside_root,
        base_environment={
            "USER": "tester",
            "LANG": "it_IT.UTF-8",
            "DISPLAY": ":1",
            "SSH_AUTH_SOCK": "/private/agent.sock",
            "VERY_SECRET": "must-not-cross",
        },
        host_pid=4242,
    )

    try:
        assert plan.scratch_dir.is_dir()
        assert plan.outside_sentinel.read_text(encoding="utf-8") == "pi-ui-outside-sentinel\n"
        assert (plan.scratch_dir / "probe.mjs").is_file()
        assert (plan.scratch_dir / "escape-link").is_symlink()
        assert (plan.scratch_dir / "escape-link").resolve() == plan.outside_sentinel

        args = plan.probe.arguments
        assert args[:4] == (
            "--unshare-all",
            "--share-net",
            "--die-with-parent",
            "--new-session",
        )
        assert "--bind" in args
        assert str(workspace.resolve()) in args
        assert str(outside_root.resolve()) not in args
        separator = args.index("--")
        assert args[separator + 1] == str(node)
        assert "/workspace/.pi-agent/.m0-gate-run-1/probe.mjs" in args
        assert str(plan.outside_sentinel) in args
        assert "4242" in args

        environment = dict(plan.environment)
        assert environment == {
            "HOME": "/home/aios",
            "LANG": "it_IT.UTF-8",
            "PATH": f"{settings.runtime_root}/bin:/usr/bin:/bin",
            "PI_OFFLINE": "1",
            "PI_SKIP_VERSION_CHECK": "1",
        }
        assert "VERY_SECRET" not in environment
        assert "DISPLAY" not in environment
        assert "SSH_AUTH_SOCK" not in environment
        assert "USER" not in environment
    finally:
        service.cleanup(plan)

    assert not plan.scratch_dir.exists()
    assert not plan.outside_run_dir.exists()
    assert not (workspace / ".pi-agent").exists()


def test_prepare_preserves_preexisting_agent_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "AIOS"
    agent_dir = workspace / ".pi-agent"
    agent_dir.mkdir(parents=True)
    marker = agent_dir / "models.json"
    marker.write_text("{}\n", encoding="utf-8")
    settings, node = _settings(tmp_path)
    service = SandboxGateService(id_factory=lambda: "run-2")

    plan = service.prepare(
        settings,
        workspace=workspace,
        node_executable=str(node),
        outside_root=tmp_path / "state",
    )
    service.cleanup(plan)

    assert agent_dir.is_dir()
    assert marker.read_text(encoding="utf-8") == "{}\n"
    assert not plan.scratch_dir.exists()


def test_parse_success_requires_all_exact_checks(tmp_path: Path) -> None:
    workspace = tmp_path / "AIOS"
    workspace.mkdir()
    settings, node = _settings(tmp_path)
    service = SandboxGateService(id_factory=lambda: "run-3")
    plan = service.prepare(
        settings,
        workspace=workspace,
        node_executable=str(node),
        outside_root=tmp_path / "state",
    )
    payload = {
        "schema": 1,
        "passed": True,
        "checks": [
            {"id": check_id, "passed": True, "detail": "verified"}
            for check_id in _CHECK_IDS
        ],
    }

    try:
        report = service.parse_result(
            plan,
            CommandProbeResult(
                probe_id="sandbox-confinement",
                exit_code=0,
                stdout=json.dumps(payload) + "\n",
                stderr="",
            ),
        )
    finally:
        service.cleanup(plan)

    assert report.passed is True
    assert len(report.checks) == len(_CHECK_IDS)
    assert all(check.status == PreflightStatus.PASS for check in report.checks)
    manifest = service.sanitized_manifest_json(report)
    assert str(workspace) not in manifest
    assert str(tmp_path) not in manifest


def test_parse_expected_confinement_failure_is_not_process_protocol_failure(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "AIOS"
    workspace.mkdir()
    settings, node = _settings(tmp_path)
    service = SandboxGateService(id_factory=lambda: "run-4")
    plan = service.prepare(
        settings,
        workspace=workspace,
        node_executable=str(node),
        outside_root=tmp_path / "state",
    )
    payload = {
        "schema": 1,
        "passed": False,
        "checks": [
            {
                "id": check_id,
                "passed": check_id != "symlink-escape",
                "detail": "read unexpectedly succeeded" if check_id == "symlink-escape" else "ok",
            }
            for check_id in _CHECK_IDS
        ],
    }

    try:
        report = service.parse_result(
            plan,
            CommandProbeResult(
                probe_id="sandbox-confinement",
                exit_code=2,
                stdout=json.dumps(payload) + "\n",
                stderr="",
            ),
        )
    finally:
        service.cleanup(plan)

    assert report.passed is False
    failed = [check for check in report.checks if check.status == PreflightStatus.FAIL]
    assert len(failed) == 1
    assert failed[0].check_id == "sandbox-symlink-escape"


def test_malformed_gate_payload_fails_closed(tmp_path: Path) -> None:
    workspace = tmp_path / "AIOS"
    workspace.mkdir()
    settings, node = _settings(tmp_path)
    service = SandboxGateService(id_factory=lambda: "run-5")
    plan = service.prepare(
        settings,
        workspace=workspace,
        node_executable=str(node),
        outside_root=tmp_path / "state",
    )

    try:
        report = service.parse_result(
            plan,
            CommandProbeResult(
                probe_id="sandbox-confinement",
                exit_code=0,
                stdout='{"schema":1,"checks":[]}\n',
                stderr="",
            ),
        )
    finally:
        service.cleanup(plan)

    assert report.passed is False
    assert report.checks[0].status == PreflightStatus.FAIL
    assert "omitted required checks" in report.checks[0].summary


def test_gate_rejects_node_outside_sandbox_mounts(tmp_path: Path) -> None:
    workspace = tmp_path / "AIOS"
    workspace.mkdir()
    settings, _node = _settings(tmp_path)
    host_only_node = _make_executable(tmp_path / "home" / "tester" / ".local" / "bin" / "node")

    with pytest.raises(SandboxGateError, match="not visible"):
        SandboxGateService(id_factory=lambda: "run-6").prepare(
            settings,
            workspace=workspace,
            node_executable=str(host_only_node),
            outside_root=tmp_path / "state",
        )
