from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject

from ui.adapters.preflight_adapter import PreflightAdapter


@dataclass
class FakePreflightController:
    running: bool = False
    status_text: str = "Preflight not run"
    fail_count: int = 0
    warning_count: int = 0
    pending_count: int = 0
    manifest: str = ""

    def __post_init__(self) -> None:
        self.state_handler = lambda: None
        self.run_calls = 0
        self.cancel_calls = 0

    def set_state_handler(self, handler) -> None:
        self.state_handler = handler

    def run(self) -> None:
        self.run_calls += 1
        self.running = True
        self.status_text = "Running host preflight"
        self.state_handler()

    def cancel(self) -> None:
        self.cancel_calls += 1
        self.running = False
        self.status_text = "Preflight cancelled"
        self.state_handler()


def test_preflight_adapter_projects_state_and_invokes_operations() -> None:
    controller = FakePreflightController()
    adapter = PreflightAdapter(controller)  # type: ignore[arg-type]
    assert isinstance(adapter, QObject)

    assert adapter.running is False
    assert adapter.statusText == "Preflight not run"
    assert adapter.runPreflight() is True
    assert controller.run_calls == 1
    assert adapter.running is True
    assert adapter.statusText == "Running host preflight"

    assert adapter.cancelPreflight() is True
    assert controller.cancel_calls == 1
    assert adapter.running is False
    assert adapter.statusText == "Preflight cancelled"
