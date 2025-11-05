"""Due-cell mark detection tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from hushdesk.pdf.duecell import DueMark, detect_due_mark  # noqa: E402


class DummyRect:
    def __init__(self, *_: float) -> None:
        pass

    def intersects(self, other: "DummyRect") -> bool:  # noqa: D401
        return True


class DummyPage:
    def __init__(self, text: str) -> None:
        self._text = text

    def get_text(self, kind: str, clip: object = None) -> str:  # noqa: D401
        return self._text

    def get_drawings(self) -> list:  # noqa: D401
        return []


class DueCellDetectionTests(unittest.TestCase):
    def test_detect_dcd_from_text_x(self) -> None:
        page = DummyPage("X")
        with patch("hushdesk.pdf.duecell.fitz", SimpleNamespace(Rect=DummyRect)):
            mark = detect_due_mark(page, 0, 1, 0, 1)
        self.assertEqual(mark, DueMark.DCD)

    def test_code_allowed_overrides_given(self) -> None:
        page = DummyPage("15 √")
        with patch("hushdesk.pdf.duecell.fitz", SimpleNamespace(Rect=DummyRect)):
            mark = detect_due_mark(page, 0, 1, 0, 1)
        self.assertEqual(mark, DueMark.CODE_ALLOWED)

    def test_detect_given_check(self) -> None:
        page = DummyPage("√")
        with patch("hushdesk.pdf.duecell.fitz", SimpleNamespace(Rect=DummyRect)):
            mark = detect_due_mark(page, 0, 1, 0, 1)
        self.assertEqual(mark, DueMark.GIVEN_CHECK)

    def test_detect_given_time(self) -> None:
        page = DummyPage("09:45")
        with patch("hushdesk.pdf.duecell.fitz", SimpleNamespace(Rect=DummyRect)):
            mark = detect_due_mark(page, 0, 1, 0, 1)
        self.assertEqual(mark, DueMark.GIVEN_TIME)

    def test_detect_none(self) -> None:
        page = DummyPage("")
        with patch("hushdesk.pdf.duecell.fitz", SimpleNamespace(Rect=DummyRect)):
            mark = detect_due_mark(page, 0, 1, 0, 1)
        self.assertEqual(mark, DueMark.NONE)


if __name__ == "__main__":
    unittest.main()
