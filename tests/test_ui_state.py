"""UI state regression tests for file selection bindings."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from hushdesk.ui.main_window import MainWindow  # noqa: E402


class MainWindowSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_file_selection_updates_source_and_pending_state(self) -> None:
        with TemporaryDirectory() as tmpdir:
            window = MainWindow(app_support_dir=Path(tmpdir))
            selected_pdf = Path(tmpdir) / "example.pdf"

            window._on_pdf_selected(selected_pdf)

            self.assertEqual(window.source_label.text(), "Source: example.pdf")
            self.assertIn("(pending)", window.audit_date_label.text())
            self.assertTrue(window.run_button.isEnabled(), "Run button should enable after selection")

            window.close()

    def test_audit_date_signal_updates_label(self) -> None:
        with TemporaryDirectory() as tmpdir:
            window = MainWindow(app_support_dir=Path(tmpdir))

            window._on_audit_date_text("11/03/2025 — Central")

            self.assertEqual(window.audit_date_label.text(), "Audit Date: 11/03/2025 — Central")

            window.close()


if __name__ == "__main__":
    unittest.main()
