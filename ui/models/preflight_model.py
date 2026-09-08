"""Qt list model for presentation-ready diagnostic checks."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from core.preflight import PreflightCheck


class CheckSource(Protocol):
    @property
    def checks(self) -> tuple[PreflightCheck, ...]: ...

    def set_checks_reset_handler(
        self,
        handler: Callable[[tuple[PreflightCheck, ...]], None],
    ) -> None: ...

    def set_check_changed_handler(
        self,
        handler: Callable[[int, PreflightCheck], None],
    ) -> None: ...


class PreflightListModel(QAbstractListModel):
    """Project a focused diagnostic controller into stable QML roles."""

    LabelRole = Qt.ItemDataRole.UserRole + 1
    StatusRole = Qt.ItemDataRole.UserRole + 2
    SummaryRole = Qt.ItemDataRole.UserRole + 3
    DetailRole = Qt.ItemDataRole.UserRole + 4

    def __init__(
        self,
        controller: CheckSource,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._checks = list(controller.checks)
        controller.set_checks_reset_handler(self._reset)
        controller.set_check_changed_handler(self._change)

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._checks)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._checks):
            return None
        item = self._checks[index.row()]
        if role == Qt.ItemDataRole.DisplayRole or role == self.LabelRole:
            return item.label
        if role == self.StatusRole:
            return str(item.status)
        if role == self.SummaryRole:
            return item.summary
        if role == self.DetailRole:
            return item.detail
        return None

    def roleNames(self) -> dict[int, bytes]:  # noqa: N802
        return {
            self.LabelRole: b"label",
            self.StatusRole: b"checkStatus",
            self.SummaryRole: b"summary",
            self.DetailRole: b"detail",
        }

    def _reset(self, checks: tuple[PreflightCheck, ...]) -> None:
        self.beginResetModel()
        self._checks = list(checks)
        self.endResetModel()

    def _change(self, index: int, check: PreflightCheck) -> None:
        if not 0 <= index < len(self._checks):
            return
        self._checks[index] = check
        model_index = self.index(index, 0)
        self.dataChanged.emit(
            model_index,
            model_index,
            [self.StatusRole, self.SummaryRole, self.DetailRole],
        )
