from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject

from ui.adapters.sandbox_gate_adapter import SandboxGateAdapter


@dataclass
class FakeGateController:
    running: bool = False
    can_run: bool = True
    status_text: str = "Sandbox gate not run"
    fail_count: int = 0
    pass_count: int = 0
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
        self.can_run = False
        self.status_text = "Running Bubblewrap confinement checks"
        self.state_handler()

    def cancel(self) -> None:
        self.cancel_calls += 1
        self.running = False
        self.can_run = True
        self.status_text = "Sandbox gate cancelled"
        self.state_handler()


def test_sandbox_gate_adapter_projects_state_and_actions() -> None:
    controller = FakeGateController()
    adapter = SandboxGateAdapter(controller)  # type: ignore[arg-type]
    assert isinstance(adapter, QObject)

    assert adapter.running is False
    assert adapter.canRun is True
    assert adapter.statusText == "Sandbox gate not run"
    assert adapter.runGate() is True
    assert controller.run_calls == 1
    assert adapter.running is True
    assert adapter.canRun is False

    assert adapter.cancelGate() is True
    assert controller.cancel_calls == 1
    assert adapter.running is False
    assert adapter.canRun is True
    assert adapter.statusText == "Sandbox gate cancelled"
