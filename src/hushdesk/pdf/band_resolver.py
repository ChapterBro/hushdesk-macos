from __future__ import annotations

import re

from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class Band:
    y0: float
    y1: float
    stage: str  # 'header'|'page'|'borrow'


DATE_RE = re.compile(r"\b\d{2}[/-]\d{2}[/-]\d{4}\b")
HEADER_SCAN_FRACTIONS = (0.15, 0.20)  # PHASE6_Y_TOL
FALLBACK_OFFSET_FRACTION = 0.12
BORROW_MAX_HEIGHT = 0.85


class BandResolver:
    """
    Minimal band resolver that supports a header→page→borrow cascade without extra deps.
    Callers pass a MuPDF page-like object that exposes ``rect`` and ``get_text('...')``.
    """

    def __init__(self) -> None:
        self._prev: Optional[Band] = None

    def resolve(self, page, prev: Optional[Band] = None) -> Optional[Band]:
        """Return the detected band or borrow ``prev`` / previous."""

        fallback = prev if isinstance(prev, Band) else self._prev
        try:
            geometry = self._page_geometry(page)
            if not geometry:
                raise ValueError("page geometry unavailable")
            x0, y0, x1, y1, height, rect_obj = geometry

            for fraction in HEADER_SCAN_FRACTIONS:
                header_bottom = y0 + height * fraction
                header_text = self._page_text(page, y_limit=header_bottom, rect=rect_obj)
                if DATE_RE.search(header_text):
                    band = Band(
                        y0=header_bottom,
                        y1=min(y1, header_bottom + height * 0.75),
                        stage="header",
                    )
                    self._prev = band
                    return band

            page_text = self._page_text(page, rect=rect_obj)
            if DATE_RE.search(page_text):
                fallback_y = y0 + height * FALLBACK_OFFSET_FRACTION
                band = Band(
                    y0=fallback_y,
                    y1=min(y1, fallback_y + height * 0.75),
                    stage="page",
                )
                self._prev = band
                return band

            if fallback:
                prev_height = fallback.y1 - fallback.y0
                if 0 < prev_height <= height * BORROW_MAX_HEIGHT:
                    borrowed = Band(y0=fallback.y0, y1=fallback.y1, stage="borrow")
                    self._prev = borrowed
                    return borrowed
        except Exception:
            pass

        if fallback:
            borrowed = Band(y0=fallback.y0, y1=fallback.y1, stage="borrow")
            self._prev = borrowed
            return borrowed
        return None

    def _page_geometry(self, page):
        rect = getattr(page, "rect", None)
        if rect is not None:
            x0 = float(getattr(rect, "x0", 0.0))
            y0 = float(getattr(rect, "y0", 0.0))
            x1 = float(getattr(rect, "x1", 0.0))
            y1 = float(getattr(rect, "y1", 0.0))
            height = float(getattr(rect, "height", 0.0) or (y1 - y0))
            if height <= 0:
                height = float((y1 - y0) or getattr(page, "height", 0.0) or 0.0)
            if height <= 0:
                return None
            return (x0, y0, x1, y1, height, rect)

        width = float(getattr(page, "width", 0.0) or 0.0)
        height = float(getattr(page, "height", 0.0) or 0.0)
        if height <= 0:
            return None
        x1 = width if width > 0 else 0.0
        return (0.0, 0.0, x1, height, height, None)

    def _page_text(self, page, *, y_limit: Optional[float] = None, rect=None) -> str:
        words = getattr(page, "words", None)
        if isinstance(words, Sequence) and words:
            tokens = []
            for word in words:
                text = str(getattr(word, "text", "")).strip()
                if not text:
                    continue
                if y_limit is not None:
                    center = getattr(word, "center", None)
                    if not center:
                        continue
                    if float(center[1]) > y_limit:
                        continue
                tokens.append(text)
            if tokens:
                return " ".join(tokens)

        raw_page = getattr(page, "raw_page", None)
        if raw_page is not None:
            try:
                if y_limit is not None and rect is not None:
                    rx0, ry0, rx1, ry1 = self._rect_components(rect)
                    clip_top = min(ry1, y_limit)
                    return raw_page.get_text("text", clip=(rx0, ry0, rx1, clip_top)) or ""
                return raw_page.get_text("text") or ""
            except Exception:
                pass

        getter = getattr(page, "get_text", None)
        if callable(getter):
            clip = None
            if y_limit is not None and rect is not None:
                rx0, ry0, rx1, ry1 = self._rect_components(rect)
                clip_top = min(ry1, y_limit)
                clip = (rx0, ry0, rx1, clip_top)
            try:
                return getter("text", clip=clip) or ""
            except Exception:
                return getter("text") or ""
        return ""

    @staticmethod
    def _rect_components(rect) -> tuple[float, float, float, float]:
        if hasattr(rect, "x0"):
            return (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))
        if isinstance(rect, Sequence) and len(rect) >= 4:
            x0, y0, x1, y1 = rect[0:4]
            return (float(x0), float(y0), float(x1), float(y1))
        raise TypeError("rect must provide coordinates")


__all__ = ["Band", "BandResolver"]
