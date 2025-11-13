"""Resolve the audit-date MAR column band with basic fallbacks."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional, Tuple

from .mar_header import band_for_date
from .mupdf_canon import CanonPage

_HEADER_SLICE_RATIO = 0.18  # PHASE6_TOLERANCE
_MIN_HEADER_WORDS = 4


@dataclass(slots=True)
class BandDecision:
    """Resolved column band paired with the detection stage."""

    band: Optional[Tuple[float, float]]
    stage: str  # 'header' | 'page' | 'borrow' | 'miss'


class BandResolver:
    """
    Resolve the MAR audit column for each canonical page.

    The resolver tracks the most recent successful band so that subsequent pages
    without reliable headers can borrow the previous span instead of failing
    outright.
    """

    def __init__(self, *, header_slice_ratio: float = _HEADER_SLICE_RATIO) -> None:
        self._prev: Optional[BandDecision] = None
        self._header_slice_ratio = max(0.0, min(header_slice_ratio, 1.0)) or _HEADER_SLICE_RATIO

    def resolve(self, page, audit_date) -> BandDecision:
        """
        Return the detected band for ``page`` and the originating stage.

        When no header match is found, borrow the previous band (if any) so that
        downstream extraction can continue without resetting the column window.
        """

        band_tuple: Optional[Tuple[float, float]] = None
        stage = "miss"

        detected = self._band_from_page(page, audit_date)

        if detected:
            # Normalize to floats to keep overlaps predictable for later tracing.
            band_tuple = (float(detected[0]), float(detected[1]))
            stage = "header"
        else:
            sliced = self._slice_header_page(page)
            if sliced is not None:
                detected = self._band_from_page(sliced, audit_date)
                if detected:
                    band_tuple = (float(detected[0]), float(detected[1]))
                    stage = "page"

        if not band_tuple and self._prev and self._prev.band:
            band_tuple = self._prev.band
            stage = "borrow"

        decision = BandDecision(band=band_tuple, stage=stage)
        if band_tuple:
            self._prev = decision
        return decision

    def _band_from_page(self, page: CanonPage, audit_date) -> Optional[Tuple[float, float]]:
        try:
            return band_for_date(page, audit_date)
        except Exception:
            return None

    def _slice_header_page(self, page: CanonPage) -> Optional[CanonPage]:
        if not isinstance(page, CanonPage):
            return None
        limit = float(page.height or 0.0) * self._header_slice_ratio
        if limit <= 0.0:
            return None
        header_words = [word for word in page.words if word.center[1] <= limit]
        if len(header_words) < _MIN_HEADER_WORDS:
            return None
        return replace(page, words=header_words)


__all__ = ["BandDecision", "BandResolver"]
