"""Flat QAbstractListModel projection of the lazy workspace hierarchy."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QModelIndex, Qt, QAbstractListModel

from controllers.workspace_browser_controller import (
    VisibleWorkspaceEntry,
    WorkspaceBrowserController,
)


class WorkspaceTreeListModel(QAbstractListModel):
    NameRole = Qt.ItemDataRole.UserRole + 1
    RelativePathRole = Qt.ItemDataRole.UserRole + 2
    KindRole = Qt.ItemDataRole.UserRole + 3
    DepthRole = Qt.ItemDataRole.UserRole + 4
    ExpandedRole = Qt.ItemDataRole.UserRole + 5
    LoadingRole = Qt.ItemDataRole.UserRole + 6
    CanExpandRole = Qt.ItemDataRole.UserRole + 7
    SizeBytesRole = Qt.ItemDataRole.UserRole + 8
    ModifiedNsRole = Qt.ItemDataRole.UserRole + 9
    HiddenRole = Qt.ItemDataRole.UserRole + 10

    def __init__(self, controller: WorkspaceBrowserController) -> None:
        super().__init__()
        self._items = list(controller.items)
        controller.set_items_handler(self._reset_items)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        if role in {self.NameRole, Qt.ItemDataRole.DisplayRole}:
            return item.name
        if role == self.RelativePathRole:
            return item.relative_path
        if role == self.KindRole:
            return str(item.kind)
        if role == self.DepthRole:
            return item.depth
        if role == self.ExpandedRole:
            return item.expanded
        if role == self.LoadingRole:
            return item.loading
        if role == self.CanExpandRole:
            return item.can_expand
        if role == self.SizeBytesRole:
            return item.size_bytes
        if role == self.ModifiedNsRole:
            return item.modified_ns
        if role == self.HiddenRole:
            return item.hidden
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            self.NameRole: QByteArray(b"name"),
            self.RelativePathRole: QByteArray(b"relativePath"),
            self.KindRole: QByteArray(b"entryKind"),
            self.DepthRole: QByteArray(b"depth"),
            self.ExpandedRole: QByteArray(b"expanded"),
            self.LoadingRole: QByteArray(b"loading"),
            self.CanExpandRole: QByteArray(b"canExpand"),
            self.SizeBytesRole: QByteArray(b"sizeBytes"),
            self.ModifiedNsRole: QByteArray(b"modifiedNs"),
            self.HiddenRole: QByteArray(b"hiddenEntry"),
        }

    def _reset_items(self, items: tuple[VisibleWorkspaceEntry, ...]) -> None:
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()
