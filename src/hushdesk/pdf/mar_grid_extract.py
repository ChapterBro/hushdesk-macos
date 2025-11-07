"""Column-restricted extraction for MAR vitals and due-cell states."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from hushdesk.pdf.dates import format_mmddyyyy
from .mar_blocks import MedBlock, block_zot, extract_med_blocks
from .mar_header import band_for_date, column_zot
from .mar_tracks import TrackSpec, find_time_rows
from .mar_tokens import bp_values, cell_state, pulse_value
from .mupdf_canon import CanonPage, CanonWord
from .qa_overlay import QAHighlights, TimeRail, VitalMark
from .room_label import format_room_label, parse_room_and_bed_from_text, validate_room
from .rules_normalize import RuleSet, parse_rules

Rect = Tuple[float, float, float, float]

_HEADER_TOP_RATIO = 0.75
ALLOWED_CODES = {4, 6, 11, 12, 15}

telemetry_suppressed = 0
_dedup_before_total = 0
_dedup_after_total = 0
_clip_tokens_before = 0
_clip_tokens_after = 0
_slot_raw_labels: set[str] = set()
_slot_ids_seen: set[str] = set()
_slot_fallback_hits = 0
_dc_column_hits = 0

_TIME_TOKEN_RE = re.compile(r"\b(?:[0-1]?\d|2[0-3]):?[0-5]\d\b")
_CHECKMARK_RE = re.compile(r"[\u221A\u2713\u2714]")
_X_TOKEN_RE = re.compile(r"(?i)\bx+\b")

DueKey = Tuple[int, str, str, str]  # (page_idx, block_id, date_disp, slot_id)


@dataclass(slots=True)
class Evidence:
    text_x: bool = False
    vec_x: bool = False
    allowed_code: Optional[int] = None  # 4,6,11,12,15
    other_code: Optional[int] = None  # any other numeric code not in allowed set
    given_time: Optional[str] = None  # "08:00" or None
    checkmark: bool = False
    sbp: Optional[int] = None
    hr: Optional[int] = None


@dataclass(slots=True)
class _DueContext:
    hall: str
    room: str
    page_index: int
    time_slot: str
    slot_id: str
    normalized_slot: str
    audit_band: Rect
    track_band: Tuple[float, float]
    bp_text: str
    hr_text: str
    due_text: str
    bp_bbox: Optional[Rect]
    hr_bbox: Optional[Rect]
    due_bbox: Rect
    rule_text: str
    rules: RuleSet
    page_pixels: Tuple[int, int]
    roi_pixels: Optional[Tuple[float, float, float, float]]


def _preview_roi_for_bounds(
    page: CanonPage,
    bounds: Rect,
    margin: float = 12.0,
) -> Tuple[Optional[Tuple[float, float, float, float]], Tuple[int, int]]:
    pixmap = getattr(page, "pixmap", None)
    pix_width = int(getattr(pixmap, "width", int(round(page.width)) or 0))
    pix_height = int(getattr(pixmap, "height", int(round(page.height)) or 0))
    if pix_width <= 0:
        pix_width = int(max(1.0, round(page.width))) or 1
    if pix_height <= 0:
        pix_height = int(max(1.0, round(page.height))) or 1
    base_width = float(page.width) if page.width else float(pix_width)
    base_height = float(page.height) if page.height else float(pix_height)
    if base_width <= 0.0:
        base_width = float(pix_width)
    if base_height <= 0.0:
        base_height = float(pix_height)
    sx = pix_width / base_width if base_width else 1.0
    sy = pix_height / base_height if base_height else 1.0
    x0, y0, x1, y1 = bounds
    left = min(x0, x1)
    top = min(y0, y1)
    width = max(0.0, abs(x1 - x0))
    height = max(0.0, abs(y1 - y0))
    roi: Optional[Tuple[float, float, float, float]]
    if width <= 0.0 or height <= 0.0:
        roi = None
    else:
        px = left * sx
        py = top * sy
        pw = width * sx
        ph = height * sy
        px -= margin
        py -= margin
        pw += margin * 2.0
        ph += margin * 2.0
        if px < 0.0:
            pw += px
            px = 0.0
        if py < 0.0:
            ph += py
            py = 0.0
        if px + pw > pix_width:
            pw = max(1.0, pix_width - px)
        if py + ph > pix_height:
            ph = max(1.0, pix_height - py)
        pw = max(1.0, pw)
        ph = max(1.0, ph)
        roi = (px, py, pw, ph)
    return roi, (pix_width, pix_height)


def _reset_dedup_stats() -> None:
    global _dedup_before_total, _dedup_after_total
    _dedup_before_total = 0
    _dedup_after_total = 0


def _reset_clip_stats() -> None:
    global _clip_tokens_before, _clip_tokens_after
    _clip_tokens_before = 0
    _clip_tokens_after = 0


def _reset_slot_stats() -> None:
    global _slot_raw_labels, _slot_ids_seen, _slot_fallback_hits
    _slot_raw_labels = set()
    _slot_ids_seen = set()
    _slot_fallback_hits = 0


def _reset_dc_stats() -> None:
    global _dc_column_hits
    _dc_column_hits = 0


def _record_slot(label: str, slot_id: str, fallback_used: bool) -> None:
    global _slot_raw_labels, _slot_ids_seen, _slot_fallback_hits
    text = (label or "").strip()
    if text:
        _slot_raw_labels.add(text)
    if slot_id:
        _slot_ids_seen.add(slot_id)
    if fallback_used:
        _slot_fallback_hits += 1


def _slot_identifier(track: TrackSpec) -> Tuple[str, bool]:
    slot_id = getattr(track, "slot_id", None)
    if slot_id:
        return slot_id, False
    fallback = _fallback_slot_id(track)
    return fallback, True


def _fallback_slot_id(track: TrackSpec) -> str:
    top = int(round(track.track_y0))
    bottom = int(round(track.track_y1))
    bp_top = int(round(track.bp_y0))
    bp_bottom = int(round(track.bp_y1))
    return f"BAND_{top}_{bottom}_{bp_top}_{bp_bottom}"


def clip_tokens(
    words: Iterable[CanonWord],
    x0: float,
    x1: float,
    y0: float,
    y1: float,
) -> List[CanonWord]:
    """
    Return words whose bounding boxes intersect the clip rectangle (x0, y0, x1, y1).
    """

    global _clip_tokens_before, _clip_tokens_after
    left = min(x0, x1)
    right = max(x0, x1)
    top = min(y0, y1)
    bottom = max(y0, y1)
    if right <= left or bottom <= top:
        return []
    clipped: List[CanonWord] = []
    for word in words:
        _clip_tokens_before += 1
        wx0, wy0, wx1, wy1 = word.bbox
        if wx1 < left or wx0 > right:
            continue
        if wy1 < top or wy0 > bottom:
            continue
        clipped.append(word)
        _clip_tokens_after += 1
    return clipped


def dedup_totals() -> Tuple[int, int]:
    """Return aggregated (before, after) dedup counters for the last run."""

    return (_dedup_before_total, _dedup_after_total)


def dc_column_totals() -> int:
    """Return the number of block-level DC column masks detected."""

    return _dc_column_hits


def _record_dc_column_hit() -> None:
    global _dc_column_hits
    _dc_column_hits += 1


def _due_key(page_idx: int, block_id: str, date_disp: str, slot_id: str) -> DueKey:
    return (page_idx, block_id, date_disp, slot_id)


@dataclass(slots=True)
class DueRecord:
    """MAR due-cell capture for a single time slot."""

    hall: str
    room: str
    page_index: int
    time_slot: str
    slot_id: str
    normalized_slot: str
    sbp: Optional[int]
    hr: Optional[int]
    bp_text: str
    hr_text: str
    due_text: str
    state: str
    code: Optional[int]
    rules: RuleSet
    parametered: bool
    rule_text: str
    bp_bbox: Optional[Rect]
    hr_bbox: Optional[Rect]
    due_bbox: Rect
    audit_band: Rect
    track_band: Tuple[float, float]
    page_pixels: Tuple[int, int]
    roi_pixels: Optional[Tuple[float, float, float, float]]
    mark_category: str = field(default="empty")

    def has_vitals(self) -> bool:
        return self.sbp is not None or self.hr is not None


@dataclass(slots=True)
class PageExtraction:
    """Per-page MAR extraction including QA highlights."""

    page: CanonPage
    blocks: List[MedBlock] = field(default_factory=list)
    records: List[DueRecord] = field(default_factory=list)
    highlights: Optional[QAHighlights] = None


def extract_pages(
    pages: Iterable[CanonPage],
    audit_date: date,
    hall: str,
    *,
    building_master: Optional[dict] = None,
) -> List[PageExtraction]:
    """Return canonical due records and QA overlays for ``pages``."""

    global telemetry_suppressed
    telemetry_suppressed = 0
    _reset_dedup_stats()
    _reset_clip_stats()
    _reset_slot_stats()
    _reset_dc_stats()

    results: List[PageExtraction] = []
    pages_seen = 0
    for page in pages:
        pages_seen += 1
        extraction = _extract_single_page(page, audit_date, hall)
        if extraction:
            results.append(extraction)
    try:
        print(f"SCOPE_OK tokens={_clip_tokens_before}->{_clip_tokens_after} page_hits={pages_seen}")
    except Exception:
        pass
    try:
        print(
            "SLOT_OK "
            f"normalized={len(_slot_ids_seen)} "
            f"distinct_slots_before={len(_slot_raw_labels)} "
            f"after={len(_slot_ids_seen)} "
            f"fallback={_slot_fallback_hits}"
        )
    except Exception:
        pass
    return results


def _extract_single_page(
    page: CanonPage,
    audit_date: date,
    hall: str,
) -> Optional[PageExtraction]:
    column_band = band_for_date(page, audit_date)
    if not column_band:
        return None

    x0, x1 = column_zot(page, *column_band)
    audit_band: Rect = (x0, 0.0, x1, page.height)
    tracks = find_time_rows(page)
    if not tracks:
        return None

    med_blocks = extract_med_blocks(page)
    for block in med_blocks:
        block.rules = parse_rules(block.text)

    header_text = _header_text(page)
    labeled_room = parse_room_and_bed_from_text(header_text)
    hall_name = (hall or "").strip()
    validated_room = validate_room(hall_name, labeled_room)
    formatted_room = format_room_label(validated_room)
    room = formatted_room or "UNKNOWN"
    record_hall = (hall_name or "UNKNOWN").upper()
    highlights = QAHighlights(page_index=page.page_index, audit_band=audit_band)
    highlights.time_rails = [
        TimeRail(y=(spec.track_y0 + spec.track_y1) / 2.0, label=_display_label(spec))
        for spec in tracks
    ]

    column_words = clip_tokens(page.words, x0, x1, 0.0, page.height)
    block_scope_cache: Dict[int, Tuple[Tuple[float, float], List[CanonWord], bool]] = {}

    def _block_scope(block_obj: MedBlock) -> Tuple[Tuple[float, float], List[CanonWord], bool]:
        cache_key = id(block_obj)
        cached = block_scope_cache.get(cache_key)
        if cached is not None:
            return cached
        band = block_zot(block_obj, page.height)
        scoped_words = clip_tokens(column_words, x0, x1, band[0], band[1])
        column_mask = _has_column_cross(page, (x0, band[0], x1, band[1]))
        block_scope_cache[cache_key] = (band, scoped_words, column_mask)
        if column_mask:
            _record_dc_column_hit()
        return block_scope_cache[cache_key]
    agg: Dict[DueKey, Evidence] = {}
    contexts: Dict[DueKey, _DueContext] = {}
    duplicate_keys: List[DueKey] = []
    date_disp = format_mmddyyyy(audit_date)

    matched_blocks = [_match_block_to_track(spec, med_blocks) for spec in tracks]
    block_ids = {
        id(block): _block_identifier(page.page_index, index, block) for index, block in enumerate(med_blocks)
    }

    for spec, block in zip(tracks, matched_blocks):
        block_id = block_ids.get(id(block)) if block is not None else None
        if block is not None:
            block_band, scoped_words, block_column_mask = _block_scope(block)
        else:
            block_band, scoped_words, block_column_mask = (None, (), False)
        _collect_due_evidence_if_strict(
            spec,
            block,
            page=page,
            block_words=scoped_words,
            block_band=block_band,
            x0=x0,
            x1=x1,
            audit_band=audit_band,
            record_hall=record_hall,
            room=room,
            highlights=highlights,
            block_id=block_id,
            date_disp=date_disp,
            column_mask=block_column_mask,
            agg=agg,
            contexts=contexts,
            duplicates=duplicate_keys,
        )

    records = _finalize_due_records(
        agg=agg,
        contexts=contexts,
        duplicates=duplicate_keys,
    )

    if not records:
        return None

    return PageExtraction(page=page, blocks=med_blocks, records=records, highlights=highlights)


def _header_text(page: CanonPage) -> str:
    """Return concatenated text from the top header band."""

    limit = page.height * (1.0 - _HEADER_TOP_RATIO)
    tokens = []
    for word in page.words:
        if word.center[1] >= limit:
            token = word.text.strip()
            if token:
                tokens.append(token)
    return " ".join(tokens)


def _words_in_band(
    words: Iterable[CanonWord],
    x0: float,
    x1: float,
    y0: float,
    y1: float,
) -> Iterator[CanonWord]:
    for word in words:
        wx0, wy0, wx1, wy1 = word.bbox
        if wx1 < x0 or wx0 > x1:
            continue
        if wy1 < y0 or wy0 > y1:
            continue
        yield word


def _words_bbox(words: Sequence[CanonWord], default: Optional[Rect] = None) -> Optional[Rect]:
    if not words:
        return default
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


def _match_block_to_track(
    spec: TrackSpec,
    blocks: Sequence[MedBlock],
    delta: float = 6.0,
) -> Optional[MedBlock]:
    center = (spec.track_y0 + spec.track_y1) / 2.0
    best_block: Optional[MedBlock] = None
    best_overlap = -1.0
    best_distance = float("inf")
    for block in blocks:
        if center < (block.y0 - delta) or center > (block.y1 + delta):
            continue
        overlap = _overlap_height(spec.track_y0, spec.track_y1, block.y0, block.y1)
        block_center = (block.y0 + block.y1) / 2.0
        distance = abs(block_center - center)
        if overlap > best_overlap or (overlap == best_overlap and distance < best_distance):
            best_block = block
            best_overlap = overlap
            best_distance = distance
    return best_block


def _overlap_height(y0: float, y1: float, other_y0: float, other_y1: float) -> float:
    top = max(y0, other_y0)
    bottom = min(y1, other_y1)
    return max(0.0, bottom - top)


def _has_drawn_cross(page: CanonPage, rect: Rect) -> bool:
    rx0, ry0, rx1, ry1 = rect
    diag_pos = False
    diag_neg = False
    for p0, p1 in page.draw_segments:
        if not _segment_intersects(p0, p1, rect):
            continue
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        if abs(dx) < 1.5 or abs(dy) < 1.5:
            continue
        slope = dy / dx if dx != 0 else math.inf
        if slope > 0:
            diag_pos = True
        else:
            diag_neg = True
        if diag_pos and diag_neg:
            return True
    return False


def _has_column_cross(page: CanonPage, rect: Rect) -> bool:
    x0, y0, x1, y1 = rect
    height = max(0.0, y1 - y0)
    width = max(0.0, x1 - x0)
    if height <= 0.0 or width <= 0.0:
        return False
    min_span = max(24.0, height * 0.75)
    diag_pos = False
    diag_neg = False
    for p0, p1 in page.draw_segments:
        if not _segment_intersects(p0, p1, rect):
            continue
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        if abs(dx) < 3.0 or abs(dy) < 3.0:
            continue
        span = math.hypot(dx, dy)
        if span < min_span:
            continue
        slope = dy / dx if dx != 0 else math.inf
        if slope > 0:
            diag_pos = True
        else:
            diag_neg = True
        if diag_pos and diag_neg:
            return True
    return False


def _segment_intersects(p0: Tuple[float, float], p1: Tuple[float, float], rect: Rect) -> bool:
    x0, y0, x1, y1 = rect
    min_x = min(p0[0], p1[0])
    max_x = max(p0[0], p1[0])
    min_y = min(p0[1], p1[1])
    max_y = max(p0[1], p1[1])
    if max_x < x0 or min_x > x1 or max_y < y0 or min_y > y1:
        return False
    return True


def _display_label(spec: TrackSpec) -> str:
    label = spec.label.strip()
    if not label:
        return spec.normalized_label.upper()
    return label


def _mark_category(state: str, code: Optional[int]) -> str:
    normalized = state.upper()
    if normalized == "DCD":
        return "dcd"
    if normalized == "CODE":
        if code in ALLOWED_CODES:
            return "allowed_code"
        return "other_code"
    if normalized == "GIVEN":
        return "given"
    return "empty"


def _collect_due_evidence_if_strict(
    track: TrackSpec,
    block: Optional[MedBlock],
    *,
    page: CanonPage,
    block_words: Sequence[CanonWord],
    block_band: Optional[Tuple[float, float]],
    x0: float,
    x1: float,
    audit_band: Rect,
    record_hall: str,
    room: str,
    highlights: QAHighlights,
    block_id: Optional[str],
    date_disp: str,
    column_mask: bool,
    agg: Dict[DueKey, Evidence],
    contexts: Dict[DueKey, _DueContext],
    duplicates: List[DueKey],
) -> None:
    global telemetry_suppressed
    rules = block.rules if block else RuleSet()
    if block is None or not getattr(rules, "strict", False) or not block_id or block_band is None:
        telemetry_suppressed += 1
        return

    block_y0, block_y1 = block_band
    cell_y0 = max(block_y0, track.track_y0)
    cell_y1 = min(block_y1, track.track_y1)
    if cell_y1 <= cell_y0:
        telemetry_suppressed += 1
        return

    bp_words = list(_words_in_band(block_words, x0, x1, track.bp_y0, track.bp_y1))
    due_words = list(_words_in_band(block_words, x0, x1, track.track_y0, track.track_y1))
    pulse_words = list(_words_in_band(block_words, x0, x1, track.pulse_y0, track.pulse_y1))

    sbp = bp_values(bp_words)
    if sbp is None:
        sbp = bp_values(due_words)

    hr = pulse_value(pulse_words)

    cell_bounds = (x0, cell_y0, x1, cell_y1)
    roi_pixels, page_pixels = _preview_roi_for_bounds(page, cell_bounds)
    has_cross = _has_drawn_cross(page, cell_bounds)
    due_bbox = _words_bbox(due_words, default=cell_bounds)
    bp_bbox = _words_bbox(bp_words)
    hr_bbox = _words_bbox(pulse_words)
    bp_text = " ".join(word.text.strip() for word in bp_words if word.text.strip())
    due_text = " ".join(word.text.strip() for word in due_words if word.text.strip())
    hr_text = " ".join(word.text.strip() for word in pulse_words if word.text.strip())

    if sbp is not None and bp_bbox and highlights is not None:
        highlights.vitals.append(VitalMark(bbox=bp_bbox, label=f"SBP {sbp}"))
    if hr is not None and hr_bbox and highlights is not None:
        highlights.vitals.append(VitalMark(bbox=hr_bbox, label=f"HR {hr}"))

    slot_id, fallback_used = _slot_identifier(track)
    _record_slot(track.label, slot_id, fallback_used)
    time_slot = _display_label(track)
    key = _due_key(page.page_index, block_id, date_disp, slot_id)
    existing = key in agg
    evidence = agg.setdefault(key, Evidence())
    if existing:
        duplicates.append(key)
    else:
        contexts[key] = _DueContext(
            hall=record_hall,
            room=room,
            page_index=page.page_index,
            time_slot=time_slot,
            slot_id=slot_id,
            normalized_slot=track.normalized_label,
            audit_band=audit_band,
            track_band=(cell_y0, cell_y1),
            bp_text=bp_text,
            hr_text=hr_text,
            due_text=due_text,
            bp_bbox=bp_bbox,
            hr_bbox=hr_bbox,
            due_bbox=due_bbox if due_bbox is not None else cell_bounds,
            rule_text=block.text,
            rules=rules,
            page_pixels=page_pixels,
            roi_pixels=roi_pixels,
        )

    if sbp is not None:
        evidence.sbp = sbp
    if hr is not None:
        evidence.hr = hr
    if has_cross:
        evidence.vec_x = True
    if column_mask:
        evidence.vec_x = True
    if _has_text_x(due_text):
        evidence.text_x = True

    state, code = cell_state(due_words, has_drawn_cross=has_cross)
    if code is not None:
        if code in ALLOWED_CODES:
            evidence.allowed_code = code
        elif evidence.allowed_code is None:
            evidence.other_code = code

    time_hit = _extract_given_time(due_text)
    if time_hit and not evidence.given_time:
        evidence.given_time = time_hit
    if _CHECKMARK_RE.search(due_text):
        evidence.checkmark = True


def _finalize_due_records(
    *,
    agg: Dict[DueKey, Evidence],
    contexts: Dict[DueKey, _DueContext],
    duplicates: Sequence[DueKey],
) -> List[DueRecord]:
    emitted: List[DueRecord] = []
    for key, evidence in agg.items():
        context = contexts.get(key)
        if context is None:
            continue
        state, code = _state_from_evidence(evidence)
        record = _build_due_record_from_ev(context, evidence, state, code)
        if record is not None:
            emitted.append(record)

    merged_before = len(duplicates) + len(agg)
    merged_after = len(emitted)
    global _dedup_before_total, _dedup_after_total
    _dedup_before_total += merged_before
    _dedup_after_total += merged_after
    return emitted


def _build_due_record_from_ev(
    context: _DueContext,
    evidence: Evidence,
    state: str,
    code: Optional[int],
) -> Optional[DueRecord]:
    rules = context.rules
    parametered = bool(getattr(rules, "strict", False))
    mark_category = _mark_category(state, code)
    return DueRecord(
        hall=context.hall,
        room=context.room,
        page_index=context.page_index,
        time_slot=context.time_slot,
        slot_id=context.slot_id,
        normalized_slot=context.normalized_slot,
        sbp=evidence.sbp,
        hr=evidence.hr,
        bp_text=context.bp_text,
        hr_text=context.hr_text,
        due_text=context.due_text,
        state=state,
        code=code,
        rules=rules,
        parametered=parametered,
        rule_text=context.rule_text,
        bp_bbox=context.bp_bbox,
        hr_bbox=context.hr_bbox,
        due_bbox=context.due_bbox,
        audit_band=context.audit_band,
        track_band=context.track_band,
        page_pixels=context.page_pixels,
        roi_pixels=context.roi_pixels,
        mark_category=mark_category,
    )


def _state_from_evidence(evidence: Evidence) -> Tuple[str, Optional[int]]:
    if evidence.text_x or evidence.vec_x:
        return ("DCD", None)
    if evidence.allowed_code is not None:
        return ("CODE", evidence.allowed_code)
    if evidence.given_time or evidence.checkmark:
        return ("GIVEN", None)
    if evidence.other_code is not None:
        return ("CODE", evidence.other_code)
    return ("EMPTY", None)


def _extract_given_time(text: str) -> Optional[str]:
    if not text:
        return None
    match = _TIME_TOKEN_RE.search(text)
    if not match:
        return None
    token = match.group(0)
    return _normalize_time_token(token)


def _normalize_time_token(token: str) -> str:
    digits = token.replace(":", "")
    if len(digits) == 3:
        digits = f"0{digits}"
    if len(digits) < 4:
        digits = digits.rjust(4, "0")
    normalized = f"{digits[:2]}:{digits[2:]}"
    return normalized


def _has_text_x(text: str) -> bool:
    if not text:
        return False
    return bool(_X_TOKEN_RE.search(text))


def _block_identifier(page_index: int, block_index: int, block: MedBlock) -> str:
    title = (block.title or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", title).strip("-")
    if not slug:
        slug = "block"
    slug = slug[:24]
    return f"p{page_index + 1}-b{block_index + 1}-{slug}"


__all__ = [
    "DueRecord",
    "PageExtraction",
    "clip_tokens",
    "extract_pages",
    "telemetry_suppressed",
    "dedup_totals",
    "dc_column_totals",
]
