"""Application bootstrap for the HushDesk macOS client."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from hushdesk.ui.main_window import MainWindow


def _ensure_application_support_dir() -> Path:
    """Ensure the Application Support directory exists and return its path."""
    app_support = Path.home() / "Library" / "Application Support" / "HushDesk"
    app_support.mkdir(parents=True, exist_ok=True)
    return app_support


def main() -> int:
    """Create the QApplication and launch the main window."""
    if not QApplication.instance():
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("HushDesk")
    app.setOrganizationName("HushDesk")

    app_support_dir = _ensure_application_support_dir()
    window = MainWindow(app_support_dir=app_support_dir)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
