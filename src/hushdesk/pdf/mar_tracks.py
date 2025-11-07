"""Track and vital row detection within canonical MAR pages."""

from __future__ import annotations

import bisect
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from .mupdf_canon import CanonLine, CanonPage, CanonWord, iter_canon_pages
from .qa_overlay import QAHighlights, TimeRail, VitalMark, draw_overlay
from .time_slots import normalize as normalize_slot


@dataclass(slots=True)
class TrackSpec:
    """Track band paired with BP / Pulse sub-rows."""

    label: str
    normalized_label: str
    slot_id: Optional[str]
    track_y0: float
    track_y1: float
    bp_y0: float
    bp_y1: float
    pulse_y0: float
    pulse_y1: float
    anchor: CanonWord

_LABELS = {
    "6a-10",
    "12p-2",
    "4pm-7",
    "0800",
    "1900",
    "am",
    "pm",
    "hs",
}

_DEFAULT_TRACK_HEIGHT = 24.0
_DEFAULT_SUBROW_HEIGHT = 18.0
_MIN_LINE_SPAN = 32.0
_BP_LABEL_RE = re.compile(r"(?i)\bbp\b")
_PULSE_LABEL_RE = re.compile(r"(?i)\b(?:hr|pulse)\b")

_TIME_LABEL_SET = {
    "6a-10",
    "12p-2",
    "4pm-7",
    "0800",
    "1900",
    "am",
    "pm",
    "hs",
}
_TIME_CLUSTER_TOLERANCE = 18.0
_LABEL_LEFT_MARGIN = 40.0
_LABEL_RIGHT_MARGIN = 120.0
_ROW_GROUP_TOLERANCE = 10.0
_ROW_PADDING = 4.0
_BP_SEARCH_MIN = 6.0
_BP_SEARCH_MAX = 36.0
_PULSE_SEARCH_MIN = 4.0
_PULSE_SEARCH_MAX = 40.0
_BP_VALUE_RE = re.compile(r"\b\d{2,3}\s*/\s*\d{0,3}\b")
_PULSE_RATE_RE = re.compile(r"\b\d{2,3}\s*/?\s*min\b", re.IGNORECASE)


@dataclass(slots=True)
class TrackRowDetection:
    """Detected time track row with optional BP/Pulse bounds."""

    label: str
    normalized_label: str
    center_y: float
    track_y0: float
    track_y1: float
    anchor: CanonWord
    bp_band: Optional[Tuple[float, float]] = None
    pulse_band: Optional[Tuple[float, float]] = None


@dataclass(slots=True)
class TrackPageSummary:
    """Detection summary for a single page."""

    page: CanonPage
    page_index: int
    band: Tuple[float, float]
    tracks: List[TrackRowDetection]
    bp_pairs: int
    pulse_pairs: int


def find_time_rows(page: CanonPage) -> List[TrackSpec]:
    """Return track descriptors with BP / Pulse sub-rows for ``page``."""

    h_lines = _collect_horizontal_lines(page.hlines)
    results: List[TrackSpec] = []
    for word in page.words:
        raw = word.text.strip()
        if not raw:
            continue
        label = _normalize_label(raw)
        if label not in _LABELS:
            continue
        track_y0, track_y1, prev_index, next_index = _track_band(word, h_lines, page.height)
        bp_y0, bp_y1 = _bp_band(track_y0, track_y1, prev_index, h_lines, page.height, page.words)
        pulse_y0, pulse_y1 = _pulse_band(track_y0, track_y1, next_index, h_lines, page.height, page.words)
        slot = normalize_slot(raw)
        results.append(
            TrackSpec(
                label=raw,
                normalized_label=label,
                slot_id=slot.slot_id if slot else None,
                track_y0=track_y0,
                track_y1=track_y1,
                bp_y0=bp_y0,
                bp_y1=bp_y1,
                pulse_y0=pulse_y0,
                pulse_y1=pulse_y1,
                anchor=word,
            )
        )

    results.sort(key=lambda spec: spec.track_y0)
    return results


def _normalize_label(text: str) -> str:
    cleaned = text.strip().lower()
    cleaned = cleaned.replace(" ", "")
    cleaned = cleaned.replace("–", "-").replace("—", "-").replace("−", "-")
    cleaned = cleaned.replace(":", "")
    return cleaned


def _collect_horizontal_lines(lines: Iterable[CanonLine]) -> List[float]:
    positions: List[float] = []
    for line in lines:
        length = abs(line.p0[0] - line.p1[0])
        if length < _MIN_LINE_SPAN:
            continue
        y = (line.p0[1] + line.p1[1]) / 2.0
        positions.append(y)
    return sorted(set(round(pos, 2) for pos in positions))


def _track_band(word: CanonWord, lines: Sequence[float], page_height: float) -> Tuple[float, float, int, int]:
    y_center = word.center[1]
    index = bisect.bisect_left(lines, y_center)
    prev_line = lines[index - 1] if index > 0 else None
    next_line = lines[index] if index < len(lines) else None

    default_half = _DEFAULT_TRACK_HEIGHT / 2.0
    track_y0 = prev_line + 1.0 if prev_line is not None else max(0.0, word.bbox[1] - default_half)
    track_y1 = next_line - 1.0 if next_line is not None else min(page_height, word.bbox[3] + default_half)

    if track_y1 <= track_y0:
        track_y0 = max(0.0, word.bbox[1] - default_half)
        track_y1 = min(page_height, word.bbox[3] + default_half)
        if track_y1 <= track_y0:
            track_y1 = min(page_height, track_y0 + _DEFAULT_TRACK_HEIGHT)

    return track_y0, track_y1, index - 1, index


def _bp_band(
    track_y0: float,
    track_y1: float,
    prev_index: int,
    lines: Sequence[float],
    page_height: float,
    words: Sequence[CanonWord],
) -> Tuple[float, float]:
    label_band = _find_label_band(words, track_y0, track_y1, upper=True)
    if label_band:
        return label_band

    prev_line = lines[prev_index] if 0 <= prev_index < len(lines) else None
    prev_prev_line = lines[prev_index - 1] if 1 <= prev_index < len(lines) else None
    return _default_sub_band(
        anchor_top=prev_prev_line,
        anchor_bottom=prev_line,
        fallback_end=track_y0,
        page_height=page_height,
        direction="above",
    )


def _pulse_band(
    track_y0: float,
    track_y1: float,
    next_index: int,
    lines: Sequence[float],
    page_height: float,
    words: Sequence[CanonWord],
) -> Tuple[float, float]:
    label_band = _find_label_band(words, track_y0, track_y1, upper=False)
    if label_band:
        return label_band

    next_line = lines[next_index] if 0 <= next_index < len(lines) else None
    next_next_line = lines[next_index + 1] if 0 <= next_index + 1 < len(lines) else None
    return _default_sub_band(
        anchor_top=next_line,
        anchor_bottom=next_next_line,
        fallback_end=track_y1,
        page_height=page_height,
        direction="below",
    )


def _find_label_band(
    words: Sequence[CanonWord],
    track_y0: float,
    track_y1: float,
    *,
    upper: bool,
) -> Tuple[float, float] | None:
    """Locate BP/Pulse label bands using text heuristics when available."""

    target_re = _BP_LABEL_RE if upper else _PULSE_LABEL_RE
    candidates: List[Tuple[float, Tuple[float, float]]] = []

    for word in words:
        if not target_re.search(word.text):
            continue
        y0, y1 = word.bbox[1], word.bbox[3]
        if upper and y1 > track_y0:
            continue
        if not upper and y0 < track_y1:
            continue
        candidates.append((word.center[1], (y0 - 4.0, y1 + 4.0)))

    if not candidates:
        return None

    candidates.sort(key=lambda item: abs(item[0] - (track_y0 if upper else track_y1)))
    band = candidates[0][1]
    top = max(0.0, band[0])
    bottom = max(top + 6.0, band[1])
    return (top, bottom)


def _default_sub_band(
    anchor_top: float | None,
    anchor_bottom: float | None,
    fallback_end: float,
    page_height: float,
    direction: str,
) -> Tuple[float, float]:
    half = _DEFAULT_SUBROW_HEIGHT / 2.0
    if direction == "above":
        bottom = anchor_bottom - 1.0 if anchor_bottom is not None else fallback_end - 1.0
        top = anchor_top + 1.0 if anchor_top is not None else bottom - _DEFAULT_SUBROW_HEIGHT
    else:
        top = anchor_top + 1.0 if anchor_top is not None else fallback_end + 1.0
        bottom = anchor_bottom - 1.0 if anchor_bottom is not None else top + _DEFAULT_SUBROW_HEIGHT

    if direction == "above":
        if anchor_top is None and anchor_bottom is None:
            bottom = fallback_end - 1.0
            top = bottom - _DEFAULT_SUBROW_HEIGHT
    else:
        if anchor_top is None and anchor_bottom is None:
            top = fallback_end + 1.0
            bottom = top + _DEFAULT_SUBROW_HEIGHT

    top = max(0.0, top)
    bottom = min(page_height, bottom)
    if bottom <= top:
        if direction == "above":
            top = max(0.0, bottom - _DEFAULT_SUBROW_HEIGHT)
        else:
            bottom = min(page_height, top + _DEFAULT_SUBROW_HEIGHT)
        if bottom <= top:
            bottom = top + _DEFAULT_SUBROW_HEIGHT
    return (top, bottom)


def _words_near_band(
    words: Sequence[CanonWord],
    x0: float,
    x1: float,
    page_width: float,
) -> List[CanonWord]:
    xmin = max(0.0, x0 - _LABEL_LEFT_MARGIN)
    xmax = min(page_width, x1 + _LABEL_RIGHT_MARGIN)
    return [word for word in words if xmin <= word.center[0] <= xmax]


def _time_label_tokens(words: Sequence[CanonWord]) -> List[Tuple[str, CanonWord]]:
    tokens: List[Tuple[str, CanonWord]] = []
    for word in words:
        normalized = _normalize_label(word.text)
        if normalized in _TIME_LABEL_SET:
            tokens.append((normalized, word))
    return tokens


def _cluster_time_tokens(tokens: Sequence[Tuple[str, CanonWord]]) -> List[Tuple[float, List[Tuple[str, CanonWord]]]]:
    clusters: List[Tuple[float, List[Tuple[str, CanonWord]]]] = []
    for normalized, word in sorted(tokens, key=lambda item: item[1].center[1]):
        y = word.center[1]
        if clusters and abs(y - clusters[-1][0]) <= _TIME_CLUSTER_TOLERANCE:
            center, members = clusters[-1]
            members.append((normalized, word))
            count = len(members)
            clusters[-1] = ((center * (count - 1) + y) / count, members)
        else:
            clusters.append((y, [(normalized, word)]))
    return clusters


def _tracks_from_clusters(
    clusters: Sequence[Tuple[float, List[Tuple[str, CanonWord]]]],
    page_height: float,
) -> List[TrackRowDetection]:
    if not clusters:
        return []

    ordered = sorted(clusters, key=lambda item: item[0])
    boundaries: List[float] = [0.0]
    for index in range(1, len(ordered)):
        prev_center = ordered[index - 1][0]
        curr_center = ordered[index][0]
        boundaries.append((prev_center + curr_center) / 2.0)
    boundaries.append(page_height)

    tracks: List[TrackRowDetection] = []
    for index, (center_y, members) in enumerate(ordered):
        anchor_norm, anchor_word = max(members, key=lambda item: len(item[1].text.strip()))
        track = TrackRowDetection(
            label=anchor_word.text.strip(),
            normalized_label=anchor_norm,
            center_y=center_y,
            track_y0=boundaries[index],
            track_y1=boundaries[index + 1],
            anchor=anchor_word,
        )
        tracks.append(track)
    return tracks


def _row_bounds(
    words: Sequence[CanonWord],
    center_y: float,
    page_height: float,
    x0: float,
    x1: float,
) -> Optional[Tuple[float, float]]:
    row_words = [
        word
        for word in words
        if abs(word.center[1] - center_y) <= _ROW_GROUP_TOLERANCE
        and (x0 - _LABEL_LEFT_MARGIN) <= word.center[0] <= (x1 + _LABEL_RIGHT_MARGIN)
    ]
    if not row_words:
        return None
    top = max(0.0, min(word.bbox[1] for word in row_words) - _ROW_PADDING)
    bottom = min(page_height, max(word.bbox[3] for word in row_words) + _ROW_PADDING)
    if bottom <= top:
        bottom = min(page_height, top + _ROW_PADDING * 2.0)
    return (top, bottom)


def _bp_candidate(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if _BP_LABEL_RE.search(stripped):
        return True
    if "/" in stripped and _BP_VALUE_RE.search(stripped):
        return True
    return False


def _pulse_candidate(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if _PULSE_LABEL_RE.search(stripped):
        return True
    if _PULSE_RATE_RE.search(stripped):
        return True
    return False


def _find_bp_band(
    track: TrackRowDetection,
    words: Sequence[CanonWord],
    x0: float,
    x1: float,
    page_height: float,
) -> Optional[Tuple[float, float]]:
    window_top = max(0.0, track.track_y0 - _BP_SEARCH_MAX)
    window_bottom = max(window_top, track.track_y0 - _BP_SEARCH_MIN)
    candidates = [
        word
        for word in words
        if window_top <= word.center[1] <= window_bottom and _bp_candidate(word.text)
    ]
    if not candidates:
        return None

    candidates.sort(key=lambda word: abs(word.center[1] - track.track_y0))
    anchor = candidates[0]
    bounds = _row_bounds(words, anchor.center[1], page_height, x0, x1)
    if bounds is None:
        top = max(0.0, anchor.bbox[1] - _ROW_PADDING)
        bottom = min(page_height, anchor.bbox[3] + _ROW_PADDING)
        bounds = (top, bottom)
    return bounds


def _find_pulse_band(
    track: TrackRowDetection,
    words: Sequence[CanonWord],
    x0: float,
    x1: float,
    page_height: float,
) -> Optional[Tuple[float, float]]:
    window_top = track.track_y1 + _PULSE_SEARCH_MIN
    window_bottom = min(page_height, track.track_y1 + _PULSE_SEARCH_MAX)
    if window_top >= window_bottom:
        return None

    candidates = [
        word
        for word in words
        if window_top <= word.center[1] <= window_bottom and _pulse_candidate(word.text)
    ]
    if not candidates:
        return None

    candidates.sort(key=lambda word: abs(word.center[1] - track.track_y1))
    anchor = candidates[0]
    bounds = _row_bounds(words, anchor.center[1], page_height, x0, x1)
    if bounds is None:
        top = max(0.0, anchor.bbox[1] - _ROW_PADDING)
        bottom = min(page_height, anchor.bbox[3] + _ROW_PADDING)
        bounds = (top, bottom)
    return bounds


def detect_tracks_on_page(page: CanonPage, band: Tuple[float, float]) -> Optional[TrackPageSummary]:
    """Return track detection summary for ``page`` restricted to ``band``."""

    x0, x1 = band
    candidate_words = _words_near_band(page.words, x0, x1, page.width)
    time_tokens = _time_label_tokens(candidate_words)
    if not time_tokens:
        return None

    clusters = _cluster_time_tokens(time_tokens)
    tracks = _tracks_from_clusters(clusters, page.height)
    if not tracks:
        return None

    for track in tracks:
        track.bp_band = _find_bp_band(track, candidate_words, x0, x1, page.height)
        track.pulse_band = _find_pulse_band(track, candidate_words, x0, x1, page.height)

    bp_pairs = sum(1 for track in tracks if track.bp_band is not None)
    pulse_pairs = sum(1 for track in tracks if track.pulse_band is not None)
    return TrackPageSummary(
        page=page,
        page_index=-1,
        band=band,
        tracks=tracks,
        bp_pairs=bp_pairs,
        pulse_pairs=pulse_pairs,
    )


def locate_vitals_page(pages: Sequence[CanonPage], audit_date: date) -> Optional[TrackPageSummary]:
    """Return the first page containing time tracks and BP evidence for ``audit_date``."""

    from .mar_header import band_for_date

    for index, page in enumerate(pages):
        band = band_for_date(page, audit_date)
        if not band:
            continue
        summary = detect_tracks_on_page(page, band)
        if summary is None:
            continue
        if not summary.tracks or summary.bp_pairs == 0:
            continue
        summary.page_index = index
        return summary
    return None


def _render_track_overlay(summary: TrackPageSummary) -> Path:
    x0, x1 = summary.band
    page = summary.page
    highlights = QAHighlights(
        page_index=summary.page_index + 1,
        audit_band=(x0, 0.0, x1, page.height),
    )
    highlights.time_rails = [
        TimeRail(y=(track.track_y0 + track.track_y1) / 2.0, label=track.label)
        for track in summary.tracks
    ]
    for track in summary.tracks:
        if track.bp_band:
            highlights.vitals.append(
                VitalMark(
                    bbox=(x0, track.bp_band[0], x1, track.bp_band[1]),
                    label="BP row",
                )
            )
        if track.pulse_band:
            highlights.vitals.append(
                VitalMark(
                    bbox=(x0, track.pulse_band[0], x1, track.pulse_band[1]),
                    label="Pulse row",
                )
            )

    output = draw_overlay(page.pixmap, highlights, out_dir="debug")
    target = Path("debug") / f"qa_p{summary.page_index + 1}_tracks.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    if output != target:
        if target.exists():
            target.unlink()
        output.replace(target)
    return target


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry to detect vitals page and produce QA overlays."""

    args = list(argv) if argv is not None else sys.argv
    if len(args) != 2:
        print("Usage: python -m hushdesk.pdf.mar_tracks <pdf-path>", file=sys.stderr)
        print("TRACKS_MISS page=?")
        return 1

    pdf_path = Path(args[1]).expanduser()
    if not pdf_path.exists():
        print(f"Missing PDF: {pdf_path}", file=sys.stderr)
        print("TRACKS_MISS page=?")
        return 1

    from .mar_header import audit_date_from_filename

    try:
        audit_dt, _ = audit_date_from_filename(pdf_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        print("TRACKS_MISS page=?")
        return 1

    pages = list(iter_canon_pages(pdf_path))
    summary = locate_vitals_page(pages, audit_dt.date())
    if summary is None:
        print("TRACKS_MISS page=?")
        return 1

    _render_track_overlay(summary)
    print(
        "TRACKS_OK "
        f"page={summary.page_index + 1} "
        f"tracks={len(summary.tracks)} "
        f"bp_pairs={summary.bp_pairs} "
        f"pulse_pairs={summary.pulse_pairs}"
    )
    return 0


__all__ = [
    "TrackSpec",
    "TrackRowDetection",
    "TrackPageSummary",
    "detect_tracks_on_page",
    "find_time_rows",
    "locate_vitals_page",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
