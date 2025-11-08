"""Shared synthetic values for worker decision tests."""

from __future__ import annotations

from hushdesk.pdf.columns import ColumnBand
from hushdesk.pdf.rows import RowBands

BASE_COLUMN_BAND = ColumnBand(
    page_index=0,
    x0=120.0,
    x1=220.0,
    page_width=420.0,
    page_height=640.0,
    frac0=0.25,
    frac1=0.40,
)

BASE_BLOCK_BBOX = (80.0, 280.0, 260.0, 360.0)
BASE_ROOM_INFO = ("309-1", "Bridgeman")
ALLOWED_CODE_RULE_TEXT = "Hold if SBP < 110"
HR_RULE_TEXT = "Hold if HR < 60"


def build_row_bands(
    bp: tuple[float, float] | None = (300.0, 320.0),
    hr: tuple[float, float] | None = (320.0, 340.0),
    am: tuple[float, float] | None = (340.0, 360.0),
    pm: tuple[float, float] | None = (360.0, 380.0),
    auto_split: bool = False,
) -> RowBands:
    """Return a configurable ``RowBands`` fixture for tests."""

    return RowBands(bp=bp, hr=hr, am=am, pm=pm, auto_am_pm_split=auto_split)
