"""QAbstractListModel projection of the active conversation transcript."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QModelIndex, Qt, QAbstractListModel

from controllers.agent_controller import AgentController, ConversationMessage


class MessageListModel(QAbstractListModel):
    MessageIdRole = Qt.ItemDataRole.UserRole + 1
    MessageRoleRole = Qt.ItemDataRole.UserRole + 2
    TextRole = Qt.ItemDataRole.UserRole + 3
    StateRole = Qt.ItemDataRole.UserRole + 4

    def __init__(self, controller: AgentController) -> None:
        super().__init__()
        self._items = list(controller.messages)
        controller.set_messages_reset_handler(self._reset_messages)
        controller.set_message_added_handler(self._add_message)
        controller.set_message_changed_handler(self._change_message)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        if role == self.MessageIdRole:
            return item.message_id
        if role == self.MessageRoleRole:
            return item.role
        if role in {self.TextRole, Qt.ItemDataRole.DisplayRole}:
            return item.text
        if role == self.StateRole:
            return str(item.state)
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            self.MessageIdRole: QByteArray(b"messageId"),
            self.MessageRoleRole: QByteArray(b"messageRole"),
            self.TextRole: QByteArray(b"text"),
            self.StateRole: QByteArray(b"messageState"),
        }

    def _reset_messages(self, messages: tuple[ConversationMessage, ...]) -> None:
        self.beginResetModel()
        self._items = list(messages)
        self.endResetModel()

    def _add_message(self, index: int, message: ConversationMessage) -> None:
        if index != len(self._items):
            self.beginResetModel()
            self._items.insert(max(0, min(index, len(self._items))), message)
            self.endResetModel()
            return
        self.beginInsertRows(QModelIndex(), index, index)
        self._items.append(message)
        self.endInsertRows()

    def _change_message(self, index: int, message: ConversationMessage) -> None:
        if not 0 <= index < len(self._items):
            return
        self._items[index] = message
        model_index = self.index(index, 0)
        self.dataChanged.emit(
            model_index,
            model_index,
            [self.TextRole, self.StateRole],
        )
