from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from controllers.agent_controller import ConnectionState
from ui.native.app_shutdown import AppShutdownCoordinator


def _application() -> QApplication:
    instance = QApplication.instance()
    if instance is not None:
        return instance
    return QApplication([])


class FakeController:
    def __init__(self, *, has_process: bool) -> None:
        self.connection_state = (
            ConnectionState.READY if has_process else ConnectionState.DISCONNECTED
        )
        self.has_process = has_process
        self.shutdown_calls = 0

    def shutdown(self) -> None:
        self.shutdown_calls += 1
        if self.has_process:
            self.connection_state = ConnectionState.STOPPING


def test_shutdown_finishes_immediately_without_owned_process() -> None:
    _application()
    controller = FakeController(has_process=False)
    coordinator = AppShutdownCoordinator(controller, timeout_ms=500)  # type: ignore[arg-type]
    finished: list[bool] = []
    coordinator.finished.connect(lambda: finished.append(True))

    coordinator.request_shutdown()

    assert controller.shutdown_calls == 1
    assert finished == [True]
    assert coordinator.active is False


def test_shutdown_waits_for_controller_to_leave_stopping_state() -> None:
    _application()
    controller = FakeController(has_process=True)
    coordinator = AppShutdownCoordinator(controller, timeout_ms=500)  # type: ignore[arg-type]
    finished: list[bool] = []
    coordinator.finished.connect(lambda: finished.append(True))

    coordinator.request_shutdown()
    assert controller.connection_state == ConnectionState.STOPPING
    assert finished == []
    assert coordinator.active is True

    controller.connection_state = ConnectionState.DISCONNECTED
    coordinator.notify_state_changed()

    assert finished == [True]
    assert coordinator.active is False


def test_shutdown_watchdog_finishes_if_native_lifecycle_never_settles() -> None:
    _application()
    controller = FakeController(has_process=True)
    coordinator = AppShutdownCoordinator(controller, timeout_ms=20)  # type: ignore[arg-type]
    loop = QEventLoop()
    forced: list[str] = []
    watchdog = QTimer()
    watchdog.setSingleShot(True)

    coordinator.forcedTimeout.connect(forced.append)
    coordinator.finished.connect(loop.quit)
    watchdog.timeout.connect(loop.quit)

    coordinator.request_shutdown()
    watchdog.start(1_000)
    loop.exec()
    watchdog.stop()

    assert len(forced) == 1
    assert "did not settle" in forced[0]
    assert coordinator.active is False
