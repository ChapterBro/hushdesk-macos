"""Band geometry regression tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hushdesk.pdf.geometry import normalize_rect
from hushdesk.pdf.rows import RowBands, find_row_bands_for_block


class DummyPage:
    def __init__(self, text_dict: dict) -> None:
        self._text_dict = text_dict

    def get_text(self, kind: str, clip=None) -> dict:  # noqa: D401
        return self._text_dict


class BandGeometryTests(unittest.TestCase):
    def test_normalize_rect_orders_coordinates(self) -> None:
        rect = (120.0, 220.0, 80.0, 180.0)
        self.assertEqual(normalize_rect(rect), (80.0, 180.0, 120.0, 220.0))

    def test_row_bands_exist_when_block_bbox_is_inverted(self) -> None:
        spans = [
            {"text": "AM", "bbox": [12.0, 200.0, 30.0, 188.0]},
            {"text": "PM", "bbox": [14.0, 228.0, 34.0, 216.0]},
        ]
        text_dict = {"blocks": [{"lines": [{"spans": spans}]}]}
        page = DummyPage(text_dict)

        block_bbox = (0.0, 240.0, 160.0, 180.0)  # y1 < y0 before normalization
        with patch("hushdesk.pdf.rows.fitz", SimpleNamespace()):
            bands = find_row_bands_for_block(page, block_bbox)

        self.assertIsInstance(bands, RowBands)
        self.assertIsNotNone(bands.am)
        self.assertIsNotNone(bands.pm)
        self.assertGreater(bands.am[1], bands.am[0])
        self.assertGreater(bands.pm[1], bands.pm[0])


if __name__ == "__main__":
    unittest.main()
