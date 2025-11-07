"""MAR header parsing and audit column helpers."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from zoneinfo import ZoneInfo

from .mupdf_canon import CanonLine, CanonPage, CanonWord, build_canon_page
from .qa_overlay import QAHighlights, draw_overlay

try:  # pragma: no cover - optional dependency for CLI execution
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

_FILENAME_DATE_PATTERNS: Sequence[Tuple[str, str]] = (
    (r"\b\d{4}-\d{2}-\d{2}\b", "%Y-%m-%d"),
    (r"\b\d{2}-\d{2}-\d{4}\b", "%m-%d-%Y"),
    (r"\b\d{2}_\d{2}_\d{4}\b", "%m_%d_%Y"),
    (r"\b\d{4}_\d{2}_\d{2}\b", "%Y_%m_%d"),
)

_DAY_PATTERN = re.compile(r"^(?:[1-9]|[12]\d|3[01])$")
_HEADER_Y_RATIO = 0.25
_CLUSTER_Y_TOLERANCE = 6.0
_VERTICAL_SPAN_RATIO = 0.40
_VERTICAL_MARGIN = 12.0
_VERTICAL_SNAP_TOLERANCE = 3.0


@dataclass(slots=True)
class HeaderDetection:
    """Detected header tokens and per-day column spans."""

    tokens: List[Dict[str, float | int]]
    day_bands: Dict[int, Tuple[float, float]]


def parse_filename_date(path: str | Path) -> Optional[date]:
    """Return the first filename date match using supported patterns."""

    stem = Path(path).stem
    for pattern, fmt in _FILENAME_DATE_PATTERNS:
        match = re.search(pattern, stem)
        if not match:
            continue
        try:
            return datetime.strptime(match.group(0), fmt).date()
        except ValueError:
            continue
    return None


def audit_date_from_filename(path: str | Path, tz: str | ZoneInfo = "America/Chicago") -> Tuple[datetime, str]:
    """Return the Central audit datetime (filename date - 1 day) and display string."""

    source_date = parse_filename_date(path)
    if source_date is None:
        raise ValueError(f"Could not derive source date from filename: {Path(path).name}")

    zone = ZoneInfo(tz) if isinstance(tz, str) else tz
    localized = datetime.combine(source_date, time.min, tzinfo=zone)
    audit_dt = localized - timedelta(days=1)
    return audit_dt, audit_dt.strftime("%m/%d/%Y")


def find_day_tokens(page: CanonPage) -> List[Dict[str, float | int]]:
    """Return canonical header day tokens sorted by x-center."""

    limits = (
        page.height * _HEADER_Y_RATIO,
        page.height * 0.5,
        page.height,
    )
    tokens: List[Dict[str, float | int]] = []
    for limit in limits:
        tokens = _collect_day_tokens(page.words, limit)
        if len(tokens) >= 5:
            break
    if not tokens:
        tokens = _collect_day_tokens(page.words, limits[-1])
    if not tokens:
        return []

    clusters = _cluster_tokens_by_y(tokens)
    if not clusters:
        return []

    clusters.sort(key=lambda entry: (-len(entry["items"]), entry["y_mean"]))
    dominant = clusters[0]
    return sorted(dominant["items"], key=lambda token: token["x_center"])


def detect_header(page: CanonPage) -> HeaderDetection:
    """Return header detection (tokens + per-day bands) for ``page``."""

    tokens = find_day_tokens(page)
    if not tokens:
        return HeaderDetection(tokens=[], day_bands={})
    return _build_day_bands(page, tokens)


def band_for_date(page: CanonPage, audit_date: date | datetime) -> Optional[Tuple[float, float]]:
    """Return the [x0, x1] column band for ``audit_date`` if available."""

    detection = detect_header(page)
    if not detection.day_bands:
        return None

    day_value = audit_date.day if isinstance(audit_date, (date, datetime)) else int(audit_date)
    return detection.day_bands.get(day_value)


def column_zot(page: CanonPage, x0: float, x1: float, *, margin: float = 1.0) -> Tuple[float, float]:
    """
    Tighten the audit column band to nearby tall vertical lines, if present.
    """

    width = float(getattr(page, "width", 0.0)) or max(x0, x1, 0.0)
    height = float(getattr(page, "height", 0.0))
    left, right = (x0, x1) if x0 <= x1 else (x1, x0)

    tall_lines: List[float] = []
    for line in getattr(page, "vlines", []):
        if getattr(line, "orientation", "") != "v":
            continue
        y0 = min(float(line.p0[1]), float(line.p1[1]))
        y1 = max(float(line.p0[1]), float(line.p1[1]))
        span = y1 - y0
        if height > 0.0 and span < height * _VERTICAL_SPAN_RATIO:
            continue
        x = (float(line.p0[0]) + float(line.p1[0])) / 2.0
        tall_lines.append(x)

    left_candidates = sorted([x for x in tall_lines if x <= left], reverse=True)
    right_candidates = sorted([x for x in tall_lines if x >= right])
    maybe_left = left_candidates[0] if left_candidates else left
    maybe_right = right_candidates[0] if right_candidates else right
    if maybe_right <= maybe_left:
        maybe_left, maybe_right = left, right

    trimmed_left = max(0.0, maybe_left - margin)
    trimmed_right = min(width, maybe_right + margin) if width > 0.0 else maybe_right + margin
    if trimmed_right <= trimmed_left:
        trimmed_right = min(width, trimmed_left + max(1.0, right - left)) if width > 0.0 else trimmed_left + max(1.0, right - left)
    return (trimmed_left, trimmed_right)


def _collect_day_tokens(words: Iterable[CanonWord], limit: float) -> List[Dict[str, float | int]]:
    tokens: List[Dict[str, float | int]] = []
    for word in words:
        if word.center[1] > limit:
            continue
        text = word.text.strip()
        if not text or not _DAY_PATTERN.fullmatch(text):
            continue
        tokens.append(
            {
                "x_center": float(word.center[0]),
                "y": float(word.center[1]),
                "text_int": int(text),
            }
        )
    return tokens


def _cluster_tokens_by_y(tokens: Sequence[Dict[str, float | int]]) -> List[Dict[str, object]]:
    clusters: List[Dict[str, object]] = []
    for token in sorted(tokens, key=lambda item: float(item["y"])):  # type: ignore[index]
        token_y = float(token["y"])  # type: ignore[index]
        for cluster in clusters:
            y_mean = float(cluster["y_mean"])
            if abs(token_y - y_mean) <= _CLUSTER_Y_TOLERANCE:
                cluster_items = cluster["items"]  # type: ignore[index]
                cluster_items.append(token)
                count = len(cluster_items)
                cluster["y_mean"] = (y_mean * (count - 1) + token_y) / count
                break
        else:
            clusters.append({"items": [token], "y_mean": token_y})
    return clusters


def _build_day_bands(page: CanonPage, tokens: Sequence[Dict[str, float | int]]) -> HeaderDetection:
    if not tokens:
        return HeaderDetection(tokens=[], day_bands={})

    centers = [float(token["x_center"]) for token in tokens]  # type: ignore[index]
    day_numbers = [int(token["text_int"]) for token in tokens]  # type: ignore[index]
    row_y = sum(float(token["y"]) for token in tokens) / len(tokens)  # type: ignore[index]
    min_x = min(centers)
    max_x = max(centers)

    verticals = _collect_verticals(page.vlines, row_y, min_x, max_x, page.height)

    boundaries: List[float] = [0.0]
    for idx in range(len(centers) - 1):
        boundaries.append((centers[idx] + centers[idx + 1]) / 2.0)
    boundaries.append(page.width)

    for idx in range(1, len(boundaries) - 1):
        left_center = centers[idx - 1]
        right_center = centers[idx]
        midpoint = boundaries[idx]
        candidates = [
            vx
            for vx in verticals
            if left_center < vx < right_center and abs(vx - midpoint) <= _VERTICAL_SNAP_TOLERANCE
        ]
        if candidates:
            best = min(candidates, key=lambda value: abs(value - midpoint))
            boundaries[idx] = best

    day_bands: Dict[int, Tuple[float, float]] = {}
    for idx, day in enumerate(day_numbers):
        left = float(boundaries[idx])
        right = float(boundaries[idx + 1])
        if right <= left:
            continue
        day_bands.setdefault(day, (left, right))

    return HeaderDetection(tokens=list(tokens), day_bands=day_bands)


def _collect_verticals(
    lines: Iterable[CanonLine],
    row_y: float,
    min_x: float,
    max_x: float,
    page_height: float,
) -> List[float]:
    span_threshold = page_height * _VERTICAL_SPAN_RATIO
    min_allowed = min_x - _VERTICAL_MARGIN
    max_allowed = max_x + _VERTICAL_MARGIN

    xs: List[float] = []
    seen: set[float] = set()
    for line in lines:
        top = min(line.p0[1], line.p1[1])
        bottom = max(line.p0[1], line.p1[1])
        span = bottom - top
        if span < span_threshold:
            continue
        if not (top <= row_y <= bottom):
            continue
        x = (line.p0[0] + line.p1[0]) / 2.0
        if x < min_allowed or x > max_allowed:
            continue
        rounded = round(x, 3)
        if rounded in seen:
            continue
        seen.add(rounded)
        xs.append(rounded)
    return sorted(xs)


def _render_audit_overlay(page: CanonPage, band: Tuple[float, float]) -> Path:
    highlights = QAHighlights(
        page_index=page.page_index + 1,
        audit_band=(band[0], 0.0, band[1], page.height),
    )
    output = draw_overlay(page.pixmap, highlights, out_dir="debug")
    target = Path("debug") / "qa_p1_column.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    if output != target:
        if target.exists():
            target.unlink()
        output.replace(target)
    return target


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(argv) if argv is not None else sys.argv
    if len(args) != 2:
        print("Usage: python -m hushdesk.pdf.mar_header <pdf-path>", file=sys.stderr)
        print("BAND_MISS page=1")
        return 1

    if fitz is None:
        print("BAND_MISS page=1")
        return 1

    pdf_path = Path(args[1]).expanduser()
    if not pdf_path.exists():
        print(f"Missing PDF: {pdf_path}", file=sys.stderr)
        print("BAND_MISS page=1")
        return 1

    try:
        audit_dt, display = audit_date_from_filename(pdf_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        print("BAND_MISS page=1")
        return 1

    doc = fitz.open(str(pdf_path))  # type: ignore[operator]
    try:
        page_obj = doc.load_page(0)
        canon_page = build_canon_page(0, page_obj, scale=2.0)
    finally:
        doc.close()

    detection = detect_header(canon_page)
    band = detection.day_bands.get(audit_dt.day)
    if not band:
        print("BAND_MISS page=1")
        return 1

    _render_audit_overlay(canon_page, band)
    x0, x1 = band
    print(
        "BAND_OK "
        f"date={display} page=1 x0={x0:.3f} x1={x1:.3f} "
        f"width={canon_page.width:.1f} height={canon_page.height:.1f} "
        f"tokens={len(detection.tokens)}"
    )
    return 0


__all__ = [
    "HeaderDetection",
    "audit_date_from_filename",
    "band_for_date",
    "column_zot",
    "detect_header",
    "find_day_tokens",
    "main",
    "parse_filename_date",
]


if __name__ == "__main__":
    raise SystemExit(main())
