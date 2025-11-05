"""Band quality regression tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from hushdesk.pdf.layout import bands_from_day_centers  # noqa: E402


class BandQualityTests(unittest.TestCase):
    def test_duplicate_centers_merge_without_zero_width(self) -> None:
        centers = [(7, 391.1), (7, 391.1)]
        bands = bands_from_day_centers(centers, page_width=612.0, page_height=792.0)
        self.assertIn(7, bands, "Duplicate centers should still yield a band.")
        x0, x1, _, _ = bands[7]
        self.assertGreater(x1 - x0, 5.0, "Merged band width should exceed minimum threshold.")

    def test_narrow_first_band_filtered_out(self) -> None:
        centers = [(1, 100.0), (2, 103.0), (3, 200.0)]
        bands = bands_from_day_centers(centers, page_width=400.0, page_height=600.0)
        self.assertNotIn(1, bands, "Bands narrower than the minimum width should be skipped.")
        self.assertIn(2, bands, "Downstream bands should still be generated.")


if __name__ == "__main__":
    unittest.main()
