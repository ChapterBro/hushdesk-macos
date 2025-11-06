"""Application bootstrap for the HushDesk macOS client."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from hushdesk.ui.main_window import MainWindow


def _ensure_application_support_dir() -> Path:
    """Ensure the Application Support directory exists and return its path."""
    app_support = Path.home() / "Library" / "Application Support" / "HushDesk"
    app_support.mkdir(parents=True, exist_ok=True)
    return app_support


def main() -> int:
    """Create the QApplication and launch the main window."""
    print("HushDesk: launching GUI", flush=True)
    runtime_base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    print(f"HushDesk: runtime base {runtime_base}", flush=True)
    print(f"HushDesk: executable {Path(sys.executable).resolve()}", flush=True)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("HushDesk")
    app.setOrganizationName("HushDesk")

    app_support_dir = _ensure_application_support_dir()
    print(f"HushDesk: using support dir {app_support_dir}", flush=True)
    window = MainWindow(app_support_dir=app_support_dir)
    window.show()
    print("HushDesk: main window shown", flush=True)

    result = app.exec()
    print(f"HushDesk: event loop exited ({result})", flush=True)
    return result


if __name__ == "__main__":
    sys.exit(main())
