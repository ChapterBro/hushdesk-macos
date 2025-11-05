"""Detect due-cell markings within the audit-date column band."""

from __future__ import annotations

import re
from enum import Enum, auto

try:  # pragma: no cover - PyMuPDF optional in test environment
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from .geometry import normalize_rect

class DueMark(Enum):
    DCD = auto()
    CODE_ALLOWED = auto()
    GIVEN_CHECK = auto()
    GIVEN_TIME = auto()
    NONE = auto()


ALLOWED_CODES = {4, 6, 11, 12, 15}
_TIME_RE = re.compile(r"\b(?:[0-1]?\d|2[0-3]):[0-5]\d\b")


def detect_due_mark(page: "fitz.Page", x0: float, x1: float, y0: float, y1: float) -> DueMark:
    """Return the due-cell mark within ``(x0, y0, x1, y1)``."""

    if fitz is None:
        return DueMark.NONE

    nx0, ny0, nx1, ny1 = normalize_rect((x0, y0, x1, y1))
    rect = fitz.Rect(nx0, ny0, nx1, ny1)

    text_content = _extract_text(page, rect)
    if _has_cross_mark(text_content) or _has_vector_cross(page, rect):
        return DueMark.DCD

    if _contains_allowed_code(text_content):
        return DueMark.CODE_ALLOWED

    if "√" in text_content or "✔" in text_content:
        return DueMark.GIVEN_CHECK

    if _TIME_RE.search(text_content):
        return DueMark.GIVEN_TIME

    return DueMark.NONE


def _extract_text(page: "fitz.Page", rect: "fitz.Rect") -> str:
    try:
        return page.get_text("text", clip=rect)
    except RuntimeError:
        return ""


def _has_cross_mark(text: str) -> bool:
    normalized = text.strip()
    return "X" in normalized or "x" in normalized


def _contains_allowed_code(text: str) -> bool:
    for token in re.findall(r"\b(\d{1,2})\b", text):
        if int(token) in ALLOWED_CODES:
            return True
    return False


def _has_vector_cross(page: "fitz.Page", rect: "fitz.Rect") -> bool:
    """Detect vector crosses by locating opposing diagonal lines within ``rect``."""

    try:
        drawings = page.get_drawings()
    except RuntimeError:
        return False

    diag_positive = False
    diag_negative = False
    for drawing in drawings:
        for item in drawing.get("items", []):
            if not item:
                continue
            if item[0] != "l":  # type "l" denotes a line segment
                continue
            _, p0, p1 = item
            line_rect = fitz.Rect(p0, p1)
            if not rect.intersects(line_rect):
                continue
            dx = p1[0] - p0[0]
            dy = p1[1] - p0[1]
            if abs(dx) < 1e-3 or abs(dy) < 1e-3:
                continue
            slope = dy / dx
            if slope > 0:
                diag_positive = True
            else:
                diag_negative = True
            if diag_positive and diag_negative:
                return True
    return False
