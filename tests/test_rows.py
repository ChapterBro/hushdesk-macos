"""Row band detection tests."""

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

from hushdesk.pdf.rows import RowBands, find_row_bands_for_block  # noqa: E402


class DummyPage:
    def __init__(self, text_dict: dict) -> None:
        self._text_dict = text_dict

    def get_text(self, kind: str) -> dict:  # noqa: D401
        return self._text_dict


class RowBandDetectionTests(unittest.TestCase):
    def test_detects_row_bands_within_block(self) -> None:
        spans = [
            {"text": "BP", "bbox": [10.0, 100.0, 30.0, 112.0]},
            {"text": "Pulse", "bbox": [12.0, 120.0, 48.0, 132.0]},
            {"text": "AM", "bbox": [14.0, 140.0, 32.0, 152.0]},
            {"text": "PM", "bbox": [15.0, 158.0, 33.0, 170.0]},
        ]
        text_dict = {"blocks": [{"lines": [{"spans": spans}]}]}
        page = DummyPage(text_dict)

        with patch("hushdesk.pdf.rows.fitz", SimpleNamespace()):
            bands = find_row_bands_for_block(page, (0.0, 90.0, 200.0, 190.0))

        self.assertIsInstance(bands, RowBands)
        self.assertIsNotNone(bands.bp)
        self.assertIsNotNone(bands.hr)
        self.assertIsNotNone(bands.am)
        self.assertIsNotNone(bands.pm)
        self.assertLess(bands.bp[0], bands.hr[0])

    def test_inverted_span_coordinates_produce_bands(self) -> None:
        spans = [
            {"text": "BP", "bbox": [10.0, 132.0, 30.0, 120.0]},
            {"text": "HR", "bbox": [12.0, 152.0, 32.0, 140.0]},
            {"text": "AM", "bbox": [14.0, 172.0, 34.0, 160.0]},
            {"text": "PM", "bbox": [16.0, 192.0, 36.0, 180.0]},
        ]
        text_dict = {"blocks": [{"lines": [{"spans": spans}]}]}
        page = DummyPage(text_dict)

        with patch("hushdesk.pdf.rows.fitz", SimpleNamespace()):
            bands = find_row_bands_for_block(page, (0.0, 200.0, 200.0, 120.0))

        self.assertIsNotNone(bands.am)
        self.assertIsNotNone(bands.pm)
        self.assertGreater(bands.am[1], bands.am[0])
        self.assertGreater(bands.pm[1], bands.pm[0])

    def test_detects_am_pm_variants(self) -> None:
        spans = [
            {"text": "BP", "bbox": [6.0, 110.0, 24.0, 122.0]},
            {"text": "Pulse", "bbox": [8.0, 128.0, 44.0, 140.0]},
            {"text": "A.M.", "bbox": [10.0, 146.0, 28.0, 158.0]},
            {"text": "P M", "bbox": [12.0, 164.0, 30.0, 176.0]},
        ]
        text_dict = {"blocks": [{"lines": [{"spans": spans}]}]}
        page = DummyPage(text_dict)

        with patch("hushdesk.pdf.rows.fitz", SimpleNamespace()):
            bands = find_row_bands_for_block(page, (0.0, 100.0, 220.0, 200.0))

        self.assertIsNotNone(bands.am)
        self.assertIsNotNone(bands.pm)

    def test_auto_split_when_am_pm_missing(self) -> None:
        spans = [
            {"text": "BP", "bbox": [6.0, 110.0, 24.0, 122.0]},
            {"text": "Pulse", "bbox": [8.0, 128.0, 44.0, 140.0]},
        ]
        text_dict = {"blocks": [{"lines": [{"spans": spans}]}]}
        page = DummyPage(text_dict)

        with patch("hushdesk.pdf.rows.fitz", SimpleNamespace()):
            bands = find_row_bands_for_block(page, (0.0, 100.0, 220.0, 220.0))

        self.assertTrue(bands.auto_am_pm_split)
        self.assertIsNotNone(bands.am)
        self.assertIsNotNone(bands.pm)
        self.assertLess(bands.am[0], bands.pm[0])


if __name__ == "__main__":
    unittest.main()
