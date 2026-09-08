"""Read-only host runtime discovery for M0 preflight."""

from __future__ import annotations

import platform
import shutil

import PySide6
from PySide6.QtCore import qVersion

from core.preflight import HostRuntimeFacts


def collect_host_runtime_facts() -> HostRuntimeFacts:
    """Collect local version/path facts without starting subprocesses."""

    return HostRuntimeFacts(
        os_name=platform.system(),
        os_release=platform.release(),
        python_version=platform.python_version(),
        pyside_version=PySide6.__version__,
        qt_version=qVersion(),
        node_executable=shutil.which("node"),
    )
