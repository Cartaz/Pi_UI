from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtWidgets import QApplication


def _application() -> QApplication:
    instance = QApplication.instance()
    if instance is not None:
        return instance
    return QApplication([])


def test_inset_surface_scrolls_long_text_and_keeps_cursor_visible(
    tmp_path: Path,
) -> None:
    app = _application()
    engine = QQmlApplicationEngine()
    qml_root = Path(__file__).resolve().parents[1] / "ui" / "qml"
    engine.addImportPath(str(qml_root))

    long_text = "\n".join(f"line {index:02d}" for index in range(40))
    source = f'''
import QtQuick
import QtQuick.Controls
import PiUI

InsetSurface {{
    width: 320
    height: 120
    padding: 10

    TextArea {{
        id: area
        objectName: "testLongTextArea"
        anchors.fill: parent
        text: {json.dumps(long_text)}
        wrapMode: TextEdit.Wrap
        background: null
    }}
}}
'''
    fixture = tmp_path / "LongInset.qml"
    fixture.write_text(source, encoding="utf-8")

    warnings: list[str] = []
    engine.warnings.connect(
        lambda items: warnings.extend(item.toString() for item in items)
    )
    engine.load(QUrl.fromLocalFile(str(fixture)))
    app.processEvents()

    roots = engine.rootObjects()
    assert roots, "QML fixture failed to load:\n" + "\n".join(warnings)
    root = roots[0]

    viewport = root.findChild(QQuickItem, "insetViewport")
    scrollbar = root.findChild(QQuickItem, "insetVerticalScrollBar")
    area = root.findChild(QQuickItem, "testLongTextArea")
    assert viewport is not None
    assert scrollbar is not None
    assert area is not None

    viewport_height = float(viewport.property("height"))
    content_height = float(viewport.property("contentHeight"))
    assert content_height > viewport_height
    assert bool(viewport.property("interactive"))

    max_offset = content_height - viewport_height
    viewport.setProperty("contentY", max_offset)
    app.processEvents()
    assert float(viewport.property("contentY")) > 0

    area.setProperty("cursorPosition", len(long_text))
    app.processEvents()
    assert float(viewport.property("contentY")) > 0

    area.setProperty("cursorPosition", 0)
    app.processEvents()
    assert float(viewport.property("contentY")) <= 4
    assert not warnings, "QML warnings:\n" + "\n".join(warnings)

    root.deleteLater()
    engine.deleteLater()
    app.processEvents()
