"""Lightweight scanning helpers for developer-only MAR reconnaissance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, List, Literal, Optional, Sequence, Tuple

import re

try:  # pragma: no cover - optional when tests run headless
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from hushdesk.engine.rules import RuleSpec, parse_rule_text
from hushdesk.id.rooms import load_building_master, resolve_room_from_block
from hushdesk.pdf.columns import ColumnBand
from hushdesk.pdf.duecell import ALLOWED_CODES, DueMark, detect_due_mark
from hushdesk.pdf.geometry import normalize_rect
from hushdesk.pdf.rows import RowBands, find_row_bands_for_block


@dataclass(slots=True)
class Candidate:
    """Potential decision-bearing due cell detected during a scout pass."""

    page: int
    room_bed: Optional[str]
    dose: Optional[Literal["AM", "PM"]]
    has_code: bool
    has_time: bool
    rule_kinds: List[str]


_ROW_PADDING = 4.0
_TIME_RE = re.compile(r"\b(?:[0-1]?\d|2[0-3]):[0-5]\d\b")


def scan_candidates(
    doc: "fitz.Document",
    audit_date: date,
    bands: Sequence[ColumnBand],
) -> List[Candidate]:
    """Return candidate due cells that likely contain actionable decisions."""

    if fitz is None or not bands:
        return []

    building_master = load_building_master()
    candidates: List[Candidate] = []

    for band in bands:
        try:
            page = doc.load_page(band.page_index)
        except RuntimeError:
            continue

        try:
            text_dict = page.get_text("dict")
        except RuntimeError:
            continue

        rule_blocks = _find_rule_blocks(page, band, text_dict)
        if not rule_blocks:
            continue

        for block_bbox, rule_text in rule_blocks:
            rule_specs = parse_rule_text(rule_text)
            if not rule_specs:
                continue

            row_bands = find_row_bands_for_block(page, block_bbox)
            block_rect = normalize_rect(block_bbox)
            room_bed = _resolve_room_hint(text_dict, block_rect, building_master)
            slot_bands = _slot_bands(row_bands, block_rect)
            if not slot_bands:
                continue

            slot_x0 = max(band.x0, block_rect[0])
            slot_x1 = block_rect[2]
            rule_kinds = _summarize_rules(rule_specs)

            for dose_name, (y0, y1) in slot_bands:
                if y1 <= y0:
                    continue

                mark = detect_due_mark(page, slot_x0, slot_x1, y0, y1)
                cell_text = _collect_text(page, slot_x0, slot_x1, y0, y1)

                has_code = mark == DueMark.CODE_ALLOWED or _contains_allowed_code(cell_text)
                has_time = mark == DueMark.GIVEN_TIME or bool(_TIME_RE.search(cell_text))

                candidates.append(
                    Candidate(
                        page=band.page_index + 1,
                        room_bed=room_bed,
                        dose=dose_name,
                        has_code=has_code,
                        has_time=has_time,
                        rule_kinds=rule_kinds,
                    )
                )

    return candidates


def _find_rule_blocks(
    page: "fitz.Page",
    band: ColumnBand,
    text_dict: dict,
) -> List[Tuple[Tuple[float, float, float, float], str]]:
    candidates: List[Tuple[Tuple[float, float, float, float], str]] = []
    page_max_dim = max(page.rect.x1, page.rect.y1)
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            line_text = "".join(str(span.get("text", "")) for span in spans).strip()
            if not line_text or "hold" not in line_text.lower():
                continue
            bbox = _line_bbox(spans)
            if bbox is None:
                continue
            extended_x1 = min(page_max_dim, band.x1 + 160.0)
            block_bbox = normalize_rect(
                (
                    max(0.0, min(band.x0 - 120.0, bbox[0] - 12.0)),
                    max(0.0, bbox[1] - 36.0),
                    extended_x1,
                    min(page_max_dim, bbox[3] + 140.0),
                )
            )
            block_spans = list(
                _collect_spans(
                    text_dict,
                    block_bbox[0],
                    block_bbox[2],
                    block_bbox[1],
                    block_bbox[3],
                )
            )
            block_text = " ".join(
                str(span.get("text", "")).strip()
                for span in block_spans
                if span.get("text")
            ).strip()
            rule_text = block_text or line_text
            candidates.append((block_bbox, rule_text))

    if not candidates:
        return []

    candidates.sort(key=lambda item: item[0][1])
    merged: List[Tuple[Tuple[float, float, float, float], str]] = []
    current_bbox, current_text = candidates[0]
    for bbox, text in candidates[1:]:
        if abs(bbox[1] - current_bbox[1]) <= 8.0:
            current_bbox = (
                min(current_bbox[0], bbox[0]),
                min(current_bbox[1], bbox[1]),
                max(current_bbox[2], bbox[2]),
                max(current_bbox[3], bbox[3]),
            )
            current_text = f"{current_text} {text}"
        else:
            merged.append((current_bbox, current_text))
            current_bbox, current_text = bbox, text
    merged.append((current_bbox, current_text))
    return merged


def _slot_bands(
    row_bands: RowBands,
    block_rect: Tuple[float, float, float, float],
) -> List[Tuple[Literal["AM", "PM"], Tuple[float, float]]]:
    slots: List[Tuple[Literal["AM", "PM"], Tuple[float, float]]] = []
    am_band = _expand_band(row_bands.am, block_rect)
    pm_band = _expand_band(row_bands.pm, block_rect)
    if am_band is not None:
        slots.append(("AM", am_band))
    if pm_band is not None:
        slots.append(("PM", pm_band))
    if not slots:
        fallback = _expand_band((block_rect[1], block_rect[3]), block_rect)
        if fallback is not None:
            slots.append(("AM", fallback))
    return slots


def _expand_band(
    band: Optional[Tuple[float, float]],
    block_bbox: Tuple[float, float, float, float],
) -> Optional[Tuple[float, float]]:
    if band is None:
        return None
    rect = normalize_rect(block_bbox)
    block_top = rect[1]
    block_bottom = rect[3]
    top, bottom = band
    if bottom < top:
        top, bottom = bottom, top
    expanded_top = max(block_top, top - _ROW_PADDING)
    expanded_bottom = min(block_bottom, bottom + _ROW_PADDING)
    if expanded_bottom <= expanded_top:
        return None
    return expanded_top, expanded_bottom


def _resolve_room_hint(
    text_dict: dict,
    block_rect: Tuple[float, float, float, float],
    building_master: dict,
) -> Optional[str]:
    gutter_x1 = block_rect[0]
    gutter_x0 = max(0.0, gutter_x1 - 72.0)
    top = block_rect[1]
    bottom = block_rect[3]

    spans = list(_collect_spans(text_dict, gutter_x0, gutter_x1, top, bottom))
    if not spans:
        spans = list(_collect_spans(text_dict, gutter_x0, gutter_x1 + 20.0, top, bottom))
    if not spans:
        spans = list(_collect_spans(text_dict, block_rect[0], block_rect[2], top, bottom))
    if not spans:
        return None

    resolved = resolve_room_from_block(spans, building_master)
    if resolved:
        room_bed, _hall = resolved
        return room_bed
    return None


def _collect_spans(
    text_dict: dict,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
) -> Iterable[Dict[str, object]]:
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text")
                bbox = span.get("bbox")
                if not text or not bbox:
                    continue
                sx0, sy0, sx1, sy1 = normalize_rect(tuple(map(float, bbox)))
                if sx1 < x0 or sx0 > x1:
                    continue
                if sy1 < y0 or sy0 > y1:
                    continue
                yield {"text": text, "bbox": (sx0, sy0, sx1, sy1)}


def _line_bbox(spans: Sequence[dict]) -> Optional[Tuple[float, float, float, float]]:
    xs0: List[float] = []
    ys0: List[float] = []
    xs1: List[float] = []
    ys1: List[float] = []
    for span in spans:
        bbox = span.get("bbox")
        if not bbox:
            continue
        sx0, sy0, sx1, sy1 = map(float, bbox)
        xs0.append(sx0)
        ys0.append(sy0)
        xs1.append(sx1)
        ys1.append(sy1)
    if not xs0:
        return None
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def _collect_text(
    page: "fitz.Page",
    x0: float,
    x1: float,
    y0: float,
    y1: float,
) -> str:
    nx0, ny0, nx1, ny1 = normalize_rect((x0, y0, x1, y1))
    rect = fitz.Rect(nx0, ny0, nx1, ny1)
    try:
        return page.get_text("text", clip=rect).strip()
    except RuntimeError:
        return ""


def _summarize_rules(rule_specs: Sequence[RuleSpec]) -> List[str]:
    return [f"{spec.kind}{spec.threshold}" for spec in rule_specs]


def _contains_allowed_code(text: str) -> bool:
    for token in re.findall(r"\b(\d{1,2})\b", text):
        try:
            if int(token) in ALLOWED_CODES:
                return True
        except ValueError:
            continue
    return False
