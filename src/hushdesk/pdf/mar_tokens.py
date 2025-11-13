"""Token extraction helpers for MAR canonical cells."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from .mupdf_canon import CanonWord

BP_RE = re.compile(r"(\d{2,3})\s*/\s*(\d{2,3})")
PULSE_RE = re.compile(r"(?i)(?:pulse)?\s*[:\-]?\s*(\d{2,3})")
TIME_RE = re.compile(r"\b(?:[0-1]?\d|2[0-3]):?[0-5]\d\b")
CHECKMARK_RE = re.compile(r"[\u221A\u2713\u2714]")
CODE_RE = re.compile(r"\b(\d{1,2})\b")
X_RE = re.compile(r"(?i)\bx+\b")

CellState = Tuple[str, Optional[int]]
Rect = Tuple[float, float, float, float]

STRICT_BP_RE = re.compile(r"\b(\d{2,3})\s*/\s*(\d{2,3})\b")
INT_RE = re.compile(r"\b(\d{2,3})\b")
PULSE_LABEL_NEAR_RE = re.compile(r"(?i)\b(?:pulse|hr)\b")

_SBP_VERTICAL_FUSE = 8.0
_SBP_HORIZONTAL_FUSE = 10.0
_PULSE_LABEL_WINDOW = 60.0
_PULSE_LABEL_X_MARGIN = 180.0
_STABLE_LINE_TOLERANCE = 4.0


@dataclass(slots=True)
class VitalHit:
    """A detected vital within a canonical audit cell."""

    kind: str
    value: int
    bbox: Rect
    center: Tuple[float, float]
    tokens: Tuple[CanonWord, ...]


def _join_words(words: Sequence[CanonWord]) -> str:
    return " ".join(word.text for word in words if word.text.strip())


def bp_values(words_in_cell: Sequence[CanonWord]) -> Optional[int]:
    """Return the systolic BP when found within ``words_in_cell``."""

    text = _join_words(words_in_cell)
    match = BP_RE.search(text.replace("\n", " "))
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def pulse_value(words_in_cell: Sequence[CanonWord]) -> Optional[int]:
    """Return the pulse / HR value when present in ``words_in_cell``."""

    text = _join_words(words_in_cell)
    match = None
    for candidate in PULSE_RE.finditer(text):
        match = candidate
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def cell_state(words_in_cell: Sequence[CanonWord], *, has_drawn_cross: bool = False) -> CellState:
    """Classify the due-cell marking within ``words_in_cell``."""

    if has_drawn_cross:
        return ("DCD", None)

    tokens = [word.text.strip() for word in words_in_cell if word.text.strip()]
    text = " ".join(tokens)

    if any(X_RE.search(token) for token in tokens):
        return ("DCD", None)

    numeric_code = _extract_numeric_code(tokens)
    if numeric_code is not None:
        return ("CODE", numeric_code)

    if CHECKMARK_RE.search(text):
        return ("GIVEN", None)

    if TIME_RE.search(text):
        return ("GIVEN", None)

    return ("EMPTY", None)


def stitch_sbp_hits(words_in_cell: Sequence[CanonWord], cell_bounds: Rect) -> List[VitalHit]:
    """Return SBP hits discovered within ``cell_bounds`` from ``words_in_cell``."""

    tokens = [word for word in words_in_cell if word.text.strip()]
    if not tokens:
        return []

    ordered = sorted(tokens, key=lambda word: (round(word.center[1], 3), word.center[0]))
    hits: List[VitalHit] = []
    total = len(ordered)
    for start in range(total):
        for end in range(start + 1, min(total, start + 3) + 1):
            window = ordered[start:end]
            if not window:
                continue
            for candidate in _candidate_strings(window):
                match = STRICT_BP_RE.search(candidate)
                if not match:
                    continue
                try:
                    sbp_value = int(match.group(1))
                except ValueError:
                    continue
                bbox = _clip_rect(_words_bbox(window), cell_bounds)
                center = ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)
                hits.append(
                    VitalHit(
                        kind="SBP",
                        value=sbp_value,
                        bbox=bbox,
                        center=center,
                        tokens=tuple(window),
                    )
                )
                break
    return _dedup_hits(hits)


def locate_pulse_hit(
    pulse_words: Sequence[CanonWord],
    page_words: Sequence[CanonWord],
    cell_bounds: Rect,
    *,
    label_window: float = _PULSE_LABEL_WINDOW,
) -> Optional[VitalHit]:
    """Return a pulse hit within ``cell_bounds`` if located."""

    candidates = _integer_candidates(pulse_words, cell_bounds)
    if not candidates:
        return None

    center_y = (cell_bounds[1] + cell_bounds[3]) / 2.0
    label_candidates: List[CanonWord] = []

    for word in page_words:
        if not PULSE_LABEL_NEAR_RE.search(word.text):
            continue
        if abs(word.center[1] - center_y) > label_window:
            continue
        wx = word.center[0]
        if wx < (cell_bounds[0] - _PULSE_LABEL_X_MARGIN):
            continue
        if wx > (cell_bounds[2] + _PULSE_LABEL_X_MARGIN):
            continue
        label_candidates.append(word)

    if label_candidates:
        best: Optional[Tuple[float, float, VitalHit]] = None
        for label in label_candidates:
            for candidate in candidates:
                dy = abs(candidate.center[1] - label.center[1])
                dx = abs(candidate.center[0] - label.center[0])
                key = (dy, dx)
                if best is None or key < best[0:2]:
                    best = (dy, dx, candidate)
        if best is not None:
            return best[2]

    if _is_stable_line(candidates):
        ordered = sorted(candidates, key=lambda hit: abs(hit.center[1] - center_y))
        return ordered[0]

    return None


def _candidate_strings(window: Sequence[CanonWord]) -> List[str]:
    tokens = [word.text.strip() for word in window if word.text.strip()]
    if not tokens:
        return []
    candidates: List[str] = []

    def _append(seq: Sequence[str]) -> None:
        if not seq:
            return
        raw = " ".join(seq)
        normalized = "".join(seq)
        candidates.append(raw)
        if normalized != raw:
            candidates.append(normalized)

    _append(tokens)
    if len(tokens) > 1:
        reversed_tokens = list(reversed(tokens))
        if reversed_tokens != tokens:
            _append(reversed_tokens)

    deduped: List[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            deduped.append(candidate)
    return deduped


def _words_bbox(words: Sequence[CanonWord]) -> Rect:
    xs0 = [word.bbox[0] for word in words]
    ys0 = [word.bbox[1] for word in words]
    xs1 = [word.bbox[2] for word in words]
    ys1 = [word.bbox[3] for word in words]
    return (
        float(min(xs0)),
        float(min(ys0)),
        float(max(xs1)),
        float(max(ys1)),
    )


def _clip_rect(rect: Rect, bounds: Rect) -> Rect:
    x0 = max(bounds[0], rect[0])
    y0 = max(bounds[1], rect[1])
    x1 = min(bounds[2], rect[2])
    y1 = min(bounds[3], rect[3])
    return (x0, y0, x1, y1)


def _dedup_hits(hits: Sequence[VitalHit]) -> List[VitalHit]:
    results: List[VitalHit] = []
    for hit in sorted(hits, key=lambda item: (item.center[1], item.center[0], item.value)):
        duplicate = False
        for existing in results:
            if abs(hit.center[1] - existing.center[1]) <= _SBP_VERTICAL_FUSE and abs(hit.center[0] - existing.center[0]) <= _SBP_HORIZONTAL_FUSE:
                duplicate = True
                break
        if not duplicate:
            results.append(hit)
    return results


def _integer_candidates(words: Sequence[CanonWord], cell_bounds: Rect) -> List[VitalHit]:
    """Return integer candidates within the pulse cell bounds."""

    candidates: List[VitalHit] = []
    for word in words:
        text = word.text.strip()
        if not text:
            continue
        for match in INT_RE.finditer(text):
            try:
                value = int(match.group(1))
            except ValueError:
                continue
            bbox = _clip_rect(_words_bbox((word,)), cell_bounds)
            center = ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)
            candidates.append(
                VitalHit(
                    kind="HR",
                    value=value,
                    bbox=bbox,
                    center=center,
                    tokens=(word,),
                )
            )
    return candidates


def _is_stable_line(candidates: Sequence[VitalHit]) -> bool:
    if not candidates:
        return False
    centers = [hit.center[1] for hit in candidates]
    return (max(centers) - min(centers)) <= _STABLE_LINE_TOLERANCE


def _extract_numeric_code(tokens: Sequence[str]) -> Optional[int]:
    """Return the first numeric code token, allowing leading digits in alphanumerics."""

    for token in tokens:
        stripped = token.strip()
        if not stripped:
            continue
        if "/" in stripped or ":" in stripped or "-" in stripped:
            continue
        leading = re.match(r"^(\d{1,2})", stripped)
        if leading:
            digits = leading.group(1)
            try:
                return int(digits)
            except ValueError:
                continue
        for match in CODE_RE.finditer(stripped):
            try:
                return int(match.group(1))
            except ValueError:
                continue
    return None


__all__ = [
    "CellState",
    "VitalHit",
    "bp_values",
    "pulse_value",
    "cell_state",
    "stitch_sbp_hits",
    "locate_pulse_hit",
]
