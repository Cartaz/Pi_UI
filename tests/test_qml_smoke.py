from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from controllers.agent_controller import AgentController
from core.agent.runtime import PiLaunchSpec
from core.settings import AppSettings, SettingsStore
from ui.adapters import AgentAdapter
from ui.models import AgentProfileListModel, MessageListModel


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


def test_qml_shell_loads_offscreen_with_declared_dependencies(tmp_path: Path) -> None:
    app = _application()
    controller = AgentController(
        SettingsStore(tmp_path / "settings.json"),
        _unexpected_transport,
        settings=AppSettings(),
    )
    message_model = MessageListModel(controller)
    profile_model = AgentProfileListModel(controller)
    adapter = AgentAdapter(controller)

    engine = QQmlApplicationEngine()
    qml_root = Path(__file__).resolve().parents[1] / "ui" / "qml"
    engine.addImportPath(str(qml_root))
    engine.setInitialProperties(
        {
            "agentAdapter": adapter,
            "messageModel": message_model,
            "profileModel": profile_model,
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
    assert roots[0].property("title") == "Pi_UI"
    assert roots[0].property("agentAdapter") is not None
    assert not warnings, "QML warnings:\n" + "\n".join(warnings)

    roots[0].setProperty("visible", False)
    controller.shutdown()
    engine.deleteLater()
    app.processEvents()
