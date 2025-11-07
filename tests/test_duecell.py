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
    def __init__(self, *args: float | tuple[float, float]) -> None:
        if len(args) == 4:
            x0, y0, x1, y1 = args  # type: ignore[assignment]
        elif len(args) == 2:
            (x0, y0), (x1, y1) = args  # type: ignore[assignment]
        else:  # pragma: no cover - defensive
            raise ValueError("Unsupported Rect args")
        self.x0 = float(x0)
        self.y0 = float(y0)
        self.x1 = float(x1)
        self.y1 = float(y1)

    def intersects(self, other: "DummyRect") -> bool:  # noqa: D401
        return True


class DummyPage:
    def __init__(self, spans: list[tuple[str, tuple[float, float, float, float]]], drawings: list | None = None) -> None:
        self._spans = spans
        self._drawings = drawings or []

    def get_text(self, kind: str, clip: object = None) -> dict:  # noqa: D401
        if kind != "dict":
            raise AssertionError(f"Unexpected kind request: {kind}")
        return {
            "blocks": [
                {
                    "lines": [
                        {
                            "spans": [
                                {"text": text, "bbox": bbox}
                                for text, bbox in self._spans
                            ]
                        }
                    ]
                }
            ]
        }

    def get_drawings(self) -> list:  # noqa: D401
        return self._drawings


class DueCellDetectionTests(unittest.TestCase):
    def test_detect_dcd_from_text_x(self) -> None:
        page = DummyPage([("X", (0.0, 0.0, 1.0, 1.0))])
        with patch("hushdesk.pdf.duecell.fitz", SimpleNamespace(Rect=DummyRect)):
            mark = detect_due_mark(page, 0, 1, 0, 1)
        self.assertEqual(mark, DueMark.DCD)

    def test_code_allowed_overrides_given(self) -> None:
        page = DummyPage(
            [
                ("15", (0.1, 0.1, 0.4, 0.4)),
                ("√", (0.6, 0.2, 0.9, 0.5)),
            ]
        )
        with patch("hushdesk.pdf.duecell.fitz", SimpleNamespace(Rect=DummyRect)):
            mark = detect_due_mark(page, 0, 1, 0, 1)
        self.assertEqual(mark, DueMark.CODE_ALLOWED)

    def test_detect_given_check(self) -> None:
        page = DummyPage([("√", (0.0, 0.0, 1.0, 1.0))])
        with patch("hushdesk.pdf.duecell.fitz", SimpleNamespace(Rect=DummyRect)):
            mark = detect_due_mark(page, 0, 1, 0, 1)
        self.assertEqual(mark, DueMark.GIVEN_CHECK)

    def test_detect_given_time(self) -> None:
        page = DummyPage([("09:45", (0.0, 0.0, 1.0, 1.0))])
        with patch("hushdesk.pdf.duecell.fitz", SimpleNamespace(Rect=DummyRect)):
            mark = detect_due_mark(page, 0, 1, 0, 1)
        self.assertEqual(mark, DueMark.GIVEN_TIME)

    def test_detect_none(self) -> None:
        page = DummyPage([])
        with patch("hushdesk.pdf.duecell.fitz", SimpleNamespace(Rect=DummyRect)):
            mark = detect_due_mark(page, 0, 1, 0, 1)
        self.assertEqual(mark, DueMark.NONE)


if __name__ == "__main__":
    unittest.main()
