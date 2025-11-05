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

    def test_file_selection_updates_source_label_and_run_button(self) -> None:
        with TemporaryDirectory() as tmpdir:
            window = MainWindow(app_support_dir=Path(tmpdir))
            selected_pdf = Path(tmpdir) / "example.pdf"

            window._on_pdf_selected(selected_pdf)

            self.assertTrue(hasattr(window, "source_label"), "Expected Source label to be bound")
            self.assertTrue(window.run_button.isEnabled(), "Run button should enable after selection")

            window.close()


if __name__ == "__main__":
    unittest.main()
