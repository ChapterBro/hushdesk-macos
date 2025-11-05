"""Tests for semantic layout helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from hushdesk.pdf.layout import bands_from_day_centers  # noqa: E402


class LayoutMathTests(unittest.TestCase):
    def test_midpoints_across_three_days(self) -> None:
        centers = [(1, 10.0), (2, 30.0), (3, 50.0)]
        bands = bands_from_day_centers(centers, page_width=60.0, page_height=80.0)

        self.assertIn(1, bands)
        self.assertIn(2, bands)
        self.assertIn(3, bands)

        self.assertAlmostEqual(bands[1][0], 0.0)
        self.assertAlmostEqual(bands[1][1], 20.0)
        self.assertAlmostEqual(bands[2][0], 20.0)
        self.assertAlmostEqual(bands[2][1], 40.0)
        self.assertAlmostEqual(bands[3][0], 40.0)
        self.assertAlmostEqual(bands[3][1], 60.0)
        self.assertAlmostEqual(bands[2][2], 60.0)
        self.assertAlmostEqual(bands[2][3], 80.0)

    def test_duplicate_days_average_centers(self) -> None:
        centers = [(3, 50.0), (1, 10.0), (2, 30.0), (2, 32.0)]
        bands = bands_from_day_centers(centers, page_width=80.0, page_height=90.0)

        self.assertAlmostEqual(bands[2][0], 20.5)
        self.assertAlmostEqual(bands[2][1], 40.5)
        self.assertAlmostEqual(bands[1][0], 0.0)
        self.assertAlmostEqual(bands[3][1], 59.5)


if __name__ == "__main__":
    unittest.main()
