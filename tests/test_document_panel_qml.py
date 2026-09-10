from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtWidgets import QApplication

from controllers.workspace_document_controller import WorkspaceDocumentController
from core.workspace_document import load_document_preview
from ui.adapters.workspace_document_adapter import WorkspaceDocumentAdapter


class _ImmediateDocumentRunner:
    def submit(self, request_id, root, relative_path, max_bytes, callback) -> None:
        callback(
            request_id,
            load_document_preview(root, relative_path, max_bytes=max_bytes),
        )

    def cancel_all(self) -> None:
        return


def _application() -> QApplication:
    instance = QApplication.instance()
    if instance is not None:
        return instance
    return QApplication([])


def test_document_panel_preserves_plain_text_and_is_read_only(tmp_path: Path) -> None:
    app = _application()
    expected = "prima\r\nseconda\nUnicode: 🌍\n"
    (tmp_path / "note.txt").write_bytes(expected.encode("utf-8"))
    controller = WorkspaceDocumentController(lambda: tmp_path, _ImmediateDocumentRunner())
    adapter = WorkspaceDocumentAdapter(controller)
    adapter.openPath("note.txt")
    assert adapter.text == expected

    engine = QQmlApplicationEngine()
    qml_root = Path(__file__).resolve().parents[1] / "ui" / "qml"
    engine.addImportPath(str(qml_root))
    engine.setInitialProperties({"documentAdapter": adapter})
    warnings: list[str] = []
    engine.warnings.connect(
        lambda items: warnings.extend(item.toString() for item in items)
    )

    engine.loadFromModule("PiUI", "DocumentPanel")
    app.processEvents()

    roots = engine.rootObjects()
    assert roots, "DocumentPanel failed to load:\n" + "\n".join(warnings)
    root = roots[0]
    root.setProperty("width", 360)
    root.setProperty("height", 480)
    app.processEvents()

    preview = root.findChild(QQuickItem, "documentPreviewText")
    assert preview is not None
    assert bool(preview.property("readOnly"))
    assert preview.property("text") == expected
    assert not warnings, "QML warnings:\n" + "\n".join(warnings)

    controller.cancel()
    root.deleteLater()
    engine.deleteLater()
    app.processEvents()
