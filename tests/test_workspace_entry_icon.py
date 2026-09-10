from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication


def _application() -> QApplication:
    instance = QApplication.instance()
    if instance is not None:
        return instance
    return QApplication([])


def test_workspace_entry_icon_loads_for_each_entry_kind() -> None:
    app = _application()
    qml_root = Path(__file__).resolve().parents[1] / "ui" / "qml"

    for kind in ("directory", "file", "symlink", "other"):
        engine = QQmlApplicationEngine()
        engine.addImportPath(str(qml_root))
        engine.setInitialProperties({"kind": kind})
        warnings: list[str] = []
        engine.warnings.connect(
            lambda items, target=warnings: target.extend(item.toString() for item in items)
        )

        engine.loadFromModule("PiUI", "WorkspaceEntryIcon")
        app.processEvents()

        roots = engine.rootObjects()
        assert roots, f"{kind} icon failed to load:\n" + "\n".join(warnings)
        icon = roots[0]
        assert icon.property("kind") == kind
        assert float(icon.property("implicitWidth")) == 16
        assert float(icon.property("implicitHeight")) == 16
        assert not warnings, f"{kind} icon warnings:\n" + "\n".join(warnings)

        icon.deleteLater()
        engine.deleteLater()
        app.processEvents()


def test_workspace_panel_uses_compact_rows_and_type_icons() -> None:
    panel_qml = (
        Path(__file__).resolve().parents[1]
        / "ui"
        / "qml"
        / "PiUI"
        / "WorkspacePanel.qml"
    ).read_text(encoding="utf-8")

    assert "height: 30" in panel_qml
    assert "WorkspaceEntryIcon" in panel_qml
    assert "spacing: 0" in panel_qml
