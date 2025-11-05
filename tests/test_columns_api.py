"""Tests for column band selection API."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from typing import List
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from hushdesk.pdf.columns import ColumnBand, select_audit_columns  # noqa: E402


class DummyRect:
    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height


class DummyPage:
    def __init__(self, index: int, width: float, height: float) -> None:
        self.index = index
        self.rect = DummyRect(width, height)


class DummyDocument:
    def __init__(self, pages: List[DummyPage]) -> None:
        self._pages = pages
        self.page_count = len(pages)

    def load_page(self, index: int) -> DummyPage:
        return self._pages[index]


class ColumnSelectionTests(unittest.TestCase):
    def test_select_audit_columns_skips_pages_without_headers(self) -> None:
        pages = [
            DummyPage(index=0, width=60.0, height=90.0),
            DummyPage(index=1, width=60.0, height=90.0),
            DummyPage(index=2, width=80.0, height=100.0),
        ]
        doc = DummyDocument(pages)

        centers_per_page = [
            [(1, 10.0), (2, 30.0), (3, 50.0)],
            [],
            [(2, 35.0), (3, 55.0)],
        ]

        def fake_centers(page: DummyPage) -> List[tuple[int, float]]:
            return centers_per_page[page.index]

        with patch("hushdesk.pdf.columns.find_day_header_centers", side_effect=fake_centers):
            bands = select_audit_columns(doc, date(2025, 11, 2))

        self.assertEqual(len(bands), 2)
        self.assertTrue(all(isinstance(band, ColumnBand) for band in bands))

        self.assertEqual(bands[0].page_index, 0)
        self.assertAlmostEqual(bands[0].x0, 20.0)
        self.assertAlmostEqual(bands[0].x1, 40.0)
        self.assertAlmostEqual(bands[0].frac0, 20.0 / 60.0)
        self.assertAlmostEqual(bands[0].frac1, 40.0 / 60.0)

        self.assertEqual(bands[1].page_index, 2)
        self.assertAlmostEqual(bands[1].x0, 25.0)
        self.assertAlmostEqual(bands[1].x1, 45.0)
        self.assertAlmostEqual(bands[1].frac0, 25.0 / 80.0)
        self.assertAlmostEqual(bands[1].frac1, 45.0 / 80.0)


if __name__ == "__main__":
    unittest.main()
