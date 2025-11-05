"""Detect due-cell markings within the audit-date column band."""

from __future__ import annotations

import re
from enum import Enum, auto
from typing import Iterable, List, Tuple

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
_CHECKMARK_RE = re.compile(r"[\u221A\u2713\u2714]")


def detect_due_mark(page: "fitz.Page", x0: float, x1: float, y0: float, y1: float) -> DueMark:
    """Return the due-cell mark within ``(x0, y0, x1, y1)``."""

    if fitz is None:
        return DueMark.NONE

    nx0, ny0, nx1, ny1 = normalize_rect((x0, y0, x1, y1))
    rect = fitz.Rect(nx0, ny0, nx1, ny1)

    spans = _collect_spans(page, rect)

    if _has_cross_text(spans) or _has_vector_cross(page, rect):
        return DueMark.DCD

    if _extract_allowed_code(spans) is not None:
        return DueMark.CODE_ALLOWED

    if _has_check_mark(spans):
        return DueMark.GIVEN_CHECK

    if _has_time_entry(spans):
        return DueMark.GIVEN_TIME

    return DueMark.NONE


def _collect_spans(page: "fitz.Page", rect: "fitz.Rect") -> List[Tuple[str, Tuple[float, float, float, float]]]:
    spans: List[Tuple[str, Tuple[float, float, float, float]]] = []
    try:
        text_dict = page.get_text("dict")
    except RuntimeError:
        return spans

    target = (rect.x0, rect.y0, rect.x1, rect.y1)
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                raw_text = span.get("text")
                bbox = span.get("bbox")
                if not raw_text or not bbox:
                    continue
                normalized_bbox = normalize_rect(tuple(map(float, bbox)))
                if not _rects_intersect(normalized_bbox, target):
                    continue
                center_x = (normalized_bbox[0] + normalized_bbox[2]) / 2.0
                if center_x < rect.x0 or center_x > rect.x1:
                    continue
                spans.append((str(raw_text), normalized_bbox))
    return spans


def _rects_intersect(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> bool:
    ax0, ay0, ax1, ay1 = normalize_rect(a)
    bx0, by0, bx1, by1 = normalize_rect(b)
    return not (ax1 < bx0 or ax0 > bx1 or ay1 < by0 or ay0 > by1)


def _has_cross_text(spans: Iterable[Tuple[str, Tuple[float, float, float, float]]]) -> bool:
    for text, _ in spans:
        stripped = text.strip()
        if "X" in stripped or "x" in stripped:
            return True
    return False


def _extract_allowed_code(spans: Iterable[Tuple[str, Tuple[float, float, float, float]]]) -> int | None:
    for raw_text, _ in spans:
        text = raw_text.strip()
        if ":" in text or "/" in text:
            continue
        for token in re.findall(r"\b(\d{1,2})\b", text):
            try:
                value = int(token)
            except ValueError:
                continue
            if value in ALLOWED_CODES:
                return value
    return None


def _has_check_mark(spans: Iterable[Tuple[str, Tuple[float, float, float, float]]]) -> bool:
    for text, _ in spans:
        if _CHECKMARK_RE.search(text):
            return True
    return False


def _has_time_entry(spans: Iterable[Tuple[str, Tuple[float, float, float, float]]]) -> bool:
    for text, _ in spans:
        if _TIME_RE.search(text):
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
