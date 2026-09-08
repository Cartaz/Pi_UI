"""QAbstractListModel projection of selectable Pi model profiles."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QModelIndex, Qt, QAbstractListModel

from controllers.agent_controller import AgentController, AgentProfile


class AgentProfileListModel(QAbstractListModel):
    LabelRole = Qt.ItemDataRole.UserRole + 1
    ProviderRole = Qt.ItemDataRole.UserRole + 2
    ModelRole = Qt.ItemDataRole.UserRole + 3
    SourceRole = Qt.ItemDataRole.UserRole + 4
    BaseUrlRole = Qt.ItemDataRole.UserRole + 5
    ApiRole = Qt.ItemDataRole.UserRole + 6

    def __init__(self, controller: AgentController) -> None:
        super().__init__()
        self._items = list(controller.profiles)
        controller.set_profiles_handler(self._reset_profiles)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        if role in {self.LabelRole, Qt.ItemDataRole.DisplayRole}:
            return item.label
        if role == self.ProviderRole:
            return item.provider
        if role == self.ModelRole:
            return item.model
        if role == self.SourceRole:
            return str(item.source)
        if role == self.BaseUrlRole:
            return item.base_url or ""
        if role == self.ApiRole:
            return item.api or ""
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            self.LabelRole: QByteArray(b"label"),
            self.ProviderRole: QByteArray(b"provider"),
            self.ModelRole: QByteArray(b"modelId"),
            self.SourceRole: QByteArray(b"profileSource"),
            self.BaseUrlRole: QByteArray(b"baseUrl"),
            self.ApiRole: QByteArray(b"api"),
        }

    def _reset_profiles(
        self,
        profiles: tuple[AgentProfile, ...],
        _selected_index: int,
    ) -> None:
        self.beginResetModel()
        self._items = list(profiles)
        self.endResetModel()
