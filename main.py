"""Pi_UI application entry point: dependency wiring only."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from controllers import (
    AgentController,
    PreflightController,
    SandboxGateController,
    WorkspaceBrowserController,
    WorkspaceDocumentController,
)
from core.agent.runtime import PiLaunchSpec
from core.settings import SettingsStore
from ui.adapters import (
    AgentAdapter,
    PreflightAdapter,
    SandboxGateAdapter,
    WorkspaceBrowserAdapter,
    WorkspaceDocumentAdapter,
)
from ui.models import (
    AgentProfileListModel,
    MessageListModel,
    PreflightListModel,
    WorkspaceTreeListModel,
)
from ui.native import (
    AppShutdownCoordinator,
    QProcessAgentTransport,
    QtDeadlineScheduler,
    QtDirectoryScanRunner,
    QtDocumentLoadRunner,
    QtProbeRunner,
    collect_host_runtime_facts,
)

LOGGER = logging.getLogger("pi_ui")


def _create_transport(
    launch_spec: PiLaunchSpec,
    startup_timeout_ms: int,
    shutdown_timeout_ms: int,
) -> QProcessAgentTransport:
    return QProcessAgentTransport(
        launch_spec,
        startup_timeout_ms=startup_timeout_ms,
        shutdown_timeout_ms=shutdown_timeout_ms,
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    QCoreApplication.setApplicationName("Pi_UI")
    QCoreApplication.setOrganizationName("Cartaz")

    app = QApplication(sys.argv)
    settings_store = SettingsStore()
    settings = settings_store.load()
    if settings_store.last_recovery is not None:
        recovery = settings_store.last_recovery
        LOGGER.warning(
            "Recovered default settings after preserving invalid config at %s: %s",
            recovery.quarantined_path,
            recovery.reason,
        )

    controller = AgentController(
        settings_store,
        _create_transport,
        settings=settings,
        deadline_scheduler_factory=QtDeadlineScheduler,
    )
    workspace_scan_runner = QtDirectoryScanRunner(app)
    workspace_browser_controller = WorkspaceBrowserController(
        lambda: controller.workspace,
        workspace_scan_runner,
    )
    document_load_runner = QtDocumentLoadRunner(app)
    workspace_document_controller = WorkspaceDocumentController(
        lambda: controller.workspace,
        document_load_runner,
    )
    host_facts = collect_host_runtime_facts()
    preflight_controller = PreflightController(
        controller,
        lambda: QtProbeRunner(app),
        host_facts,
    )
    sandbox_gate_controller = SandboxGateController(
        controller,
        lambda: QtProbeRunner(app),
        host_facts,
    )

    message_model = MessageListModel(controller)
    profile_model = AgentProfileListModel(controller)
    workspace_model = WorkspaceTreeListModel(workspace_browser_controller)
    preflight_model = PreflightListModel(preflight_controller)
    sandbox_gate_model = PreflightListModel(sandbox_gate_controller)
    agent_adapter = AgentAdapter(controller)
    workspace_adapter = WorkspaceBrowserAdapter(workspace_browser_controller)
    document_adapter = WorkspaceDocumentAdapter(
        workspace_document_controller,
        app.clipboard().setText,
    )
    preflight_adapter = PreflightAdapter(preflight_controller)
    sandbox_gate_adapter = SandboxGateAdapter(sandbox_gate_controller)

    agent_adapter.stateChanged.connect(workspace_browser_controller.sync_workspace)
    agent_adapter.stateChanged.connect(workspace_document_controller.sync_workspace)
    workspace_adapter.leafActivated.connect(document_adapter.openPath)

    engine = QQmlApplicationEngine()
    qml_root = Path(__file__).resolve().parent / "ui" / "qml"
    engine.addImportPath(str(qml_root))
    engine.setInitialProperties(
        {
            "agentAdapter": agent_adapter,
            "messageModel": message_model,
            "profileModel": profile_model,
            "workspaceAdapter": workspace_adapter,
            "workspaceModel": workspace_model,
            "documentAdapter": document_adapter,
            "preflightAdapter": preflight_adapter,
            "preflightModel": preflight_model,
            "sandboxGateAdapter": sandbox_gate_adapter,
            "sandboxGateModel": sandbox_gate_model,
        }
    )
    engine.loadFromModule("PiUI", "Main")

    if not engine.rootObjects():
        LOGGER.critical("QML shell failed to load")
        workspace_document_controller.cancel()
        document_load_runner.shutdown()
        workspace_browser_controller.cancel()
        workspace_scan_runner.shutdown()
        sandbox_gate_controller.cancel()
        preflight_controller.cancel()
        controller.shutdown()
        return 1

    shutdown_coordinator = AppShutdownCoordinator(
        controller,
        timeout_ms=settings.agent.shutdown_timeout_ms + 2_000,
        parent=app,
    )
    shutdown_coordinator.forcedTimeout.connect(LOGGER.error)
    shutdown_coordinator.finished.connect(app.quit)
    agent_adapter.stateChanged.connect(shutdown_coordinator.notify_state_changed)

    # Keep the event loop alive after the last window closes so QProcess can
    # complete its asynchronous terminate -> timeout -> kill lifecycle.
    app.setQuitOnLastWindowClosed(False)
    app.lastWindowClosed.connect(workspace_document_controller.cancel)
    app.lastWindowClosed.connect(document_load_runner.shutdown)
    app.lastWindowClosed.connect(workspace_browser_controller.cancel)
    app.lastWindowClosed.connect(workspace_scan_runner.shutdown)
    app.lastWindowClosed.connect(sandbox_gate_controller.cancel)
    app.lastWindowClosed.connect(preflight_controller.cancel)
    app.lastWindowClosed.connect(shutdown_coordinator.request_shutdown)
    app.aboutToQuit.connect(workspace_document_controller.cancel)
    app.aboutToQuit.connect(document_load_runner.shutdown)
    app.aboutToQuit.connect(workspace_browser_controller.cancel)
    app.aboutToQuit.connect(workspace_scan_runner.shutdown)
    app.aboutToQuit.connect(sandbox_gate_controller.cancel)
    app.aboutToQuit.connect(preflight_controller.cancel)
    app.aboutToQuit.connect(controller.shutdown)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
