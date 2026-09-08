from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from ui.native.deadline_scheduler import QtDeadlineScheduler


def _application() -> QCoreApplication:
    instance = QCoreApplication.instance()
    if instance is not None:
        return instance
    return QCoreApplication([])


def test_qt_deadline_scheduler_fires_on_event_loop() -> None:
    _application()
    scheduler = QtDeadlineScheduler()
    loop = QEventLoop()
    fired: list[str] = []
    watchdog = QTimer()
    watchdog.setSingleShot(True)

    def callback() -> None:
        fired.append("done")
        loop.quit()

    scheduler.call_later(10, callback)
    watchdog.timeout.connect(loop.quit)
    watchdog.start(1_000)
    loop.exec()
    watchdog.stop()

    assert fired == ["done"]


def test_qt_deadline_scheduler_cancel_is_idempotent() -> None:
    _application()
    scheduler = QtDeadlineScheduler()
    loop = QEventLoop()
    fired: list[str] = []
    watchdog = QTimer()
    watchdog.setSingleShot(True)

    handle = scheduler.call_later(10, lambda: fired.append("unexpected"))
    handle.cancel()
    handle.cancel()
    watchdog.timeout.connect(loop.quit)
    watchdog.start(50)
    loop.exec()

    assert fired == []
