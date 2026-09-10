from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtWidgets import QApplication

from controllers.agent_controller import AgentController
from controllers.preflight_controller import PreflightController
from controllers.sandbox_gate_controller import SandboxGateController
from core.agent.runtime import PiLaunchSpec
from core.preflight import HostRuntimeFacts
from core.settings import AppSettings, SettingsStore
from ui.adapters import AgentAdapter, PreflightAdapter, SandboxGateAdapter
from ui.models import AgentProfileListModel, MessageListModel, PreflightListModel


def _application() -> QApplication:
    instance = QApplication.instance()
    if instance is not None:
        return instance
    return QApplication([])


def _unexpected_transport(
    _launch_spec: PiLaunchSpec,
    _startup_timeout_ms: int,
    _shutdown_timeout_ms: int,
):
    raise AssertionError("QML smoke test must not start Pi")


def _unexpected_probe_runner():
    raise AssertionError("QML smoke test must not start preflight or sandbox probes")


def test_qml_shell_loads_offscreen_with_declared_dependencies(tmp_path: Path) -> None:
    app = _application()
    controller = AgentController(
        SettingsStore(tmp_path / "settings.json"),
        _unexpected_transport,
        settings=AppSettings(),
    )
    facts = HostRuntimeFacts(
        os_name="Linux",
        os_release="test-kernel",
        python_version="3.13.0",
        pyside_version="6.11.2",
        qt_version="6.11.2",
        node_executable=None,
    )
    preflight_controller = PreflightController(
        controller,
        _unexpected_probe_runner,
        facts,
    )
    sandbox_gate_controller = SandboxGateController(
        controller,
        _unexpected_probe_runner,
        facts,
        outside_root=tmp_path / "outside",
    )
    message_model = MessageListModel(controller)
    profile_model = AgentProfileListModel(controller)
    preflight_model = PreflightListModel(preflight_controller)
    sandbox_gate_model = PreflightListModel(sandbox_gate_controller)
    adapter = AgentAdapter(controller)
    preflight_adapter = PreflightAdapter(preflight_controller)
    sandbox_gate_adapter = SandboxGateAdapter(sandbox_gate_controller)

    engine = QQmlApplicationEngine()
    qml_root = Path(__file__).resolve().parents[1] / "ui" / "qml"
    engine.addImportPath(str(qml_root))
    engine.setInitialProperties(
        {
            "agentAdapter": adapter,
            "messageModel": message_model,
            "profileModel": profile_model,
            "preflightAdapter": preflight_adapter,
            "preflightModel": preflight_model,
            "sandboxGateAdapter": sandbox_gate_adapter,
            "sandboxGateModel": sandbox_gate_model,
        }
    )
    warnings: list[str] = []
    engine.warnings.connect(
        lambda items: warnings.extend(item.toString() for item in items)
    )

    engine.loadFromModule("PiUI", "Main")
    app.processEvents()

    roots = engine.rootObjects()
    assert roots, "QML shell failed to create a root object:\n" + "\n".join(warnings)
    root = roots[0]
    assert root.property("title") == "Pi_UI"
    assert root.property("agentAdapter") is not None
    assert root.property("preflightAdapter") is not None
    assert root.property("preflightModel") is not None
    assert root.property("sandboxGateAdapter") is not None
    assert root.property("sandboxGateModel") is not None
    assert preflight_controller.status_text == "Preflight not run"
    assert sandbox_gate_controller.status_text == "Sandbox gate not run"

    root.setProperty("width", root.property("minimumWidth"))
    root.setProperty("height", root.property("minimumHeight"))
    app.processEvents()

    header = root.findChild(QQuickItem, "headerSurface")
    connect_button = root.findChild(QQuickItem, "connectButton")
    assert header is not None
    assert connect_button is not None
    assert header.property("height") >= 133

    button_origin = connect_button.mapToItem(header, QPointF(0, 0))
    button_right = button_origin.x() + float(connect_button.property("width"))
    button_bottom = button_origin.y() + float(connect_button.property("height"))
    assert button_origin.x() >= 0
    assert button_origin.y() >= 0
    assert button_right <= float(header.property("width"))
    assert button_bottom <= float(header.property("height"))
    assert not warnings, "QML warnings:\n" + "\n".join(warnings)

    root.setProperty("visible", False)
    sandbox_gate_controller.cancel()
    preflight_controller.cancel()
    controller.shutdown()
    engine.deleteLater()
    app.processEvents()


def test_workspace_picker_accepts_the_displayed_folder() -> None:
    main_qml = (
        Path(__file__).resolve().parents[1] / "ui" / "qml" / "PiUI" / "Main.qml"
    ).read_text(encoding="utf-8")

    assert 'acceptLabel: "Use this folder"' in main_qml
    assert "setWorkspaceUrl(currentFolder)" in main_qml
    assert "setWorkspaceUrl(selectedFolder)" not in main_qml
