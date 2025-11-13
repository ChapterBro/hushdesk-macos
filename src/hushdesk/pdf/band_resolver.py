"""Resolve the audit-date MAR column band with basic fallbacks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .mar_header import band_for_date


@dataclass(slots=True)
class BandDecision:
    """Resolved column band paired with the detection stage."""

    band: Optional[Tuple[float, float]]
    stage: str  # 'header' | 'borrow' | 'miss'


class BandResolver:
    """
    Resolve the MAR audit column for each canonical page.

    The resolver tracks the most recent successful band so that subsequent pages
    without reliable headers can borrow the previous span instead of failing
    outright.
    """

    def __init__(self) -> None:
        self._prev: Optional[BandDecision] = None

    def resolve(self, page, audit_date) -> BandDecision:
        """
        Return the detected band for ``page`` and the originating stage.

        When no header match is found, borrow the previous band (if any) so that
        downstream extraction can continue without resetting the column window.
        """

        band_tuple: Optional[Tuple[float, float]] = None
        stage = "miss"

        try:
            detected = band_for_date(page, audit_date)
        except Exception:
            detected = None

        if detected:
            # Normalize to floats to keep overlaps predictable for later tracing.
            band_tuple = (float(detected[0]), float(detected[1]))
            stage = "header"
        elif self._prev and self._prev.band:
            band_tuple = self._prev.band
            stage = "borrow"

        decision = BandDecision(band=band_tuple, stage=stage)
        if band_tuple:
            self._prev = decision
        return decision


__all__ = ["BandDecision", "BandResolver"]
