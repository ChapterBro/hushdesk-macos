"""Extract blood pressure and heart rate vitals from MAR column bands."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple, Union

try:  # pragma: no cover - PyMuPDF optional when tests run
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from hushdesk.accel import stitch_bp, y_cluster

from .geometry import normalize_rect

BP_RE = re.compile(r"(?i)\b(?:bp\s*)?(\d{2,3})\s*/\s*(\d{2,3})\b")
BP_PREFIX_RE = re.compile(r"(?<!\d)(\d{2,3})\s*/\s*$")
DIGITS_ONLY_RE = re.compile(r"^\d{2,3}$")
DATE_LIKE_RE = re.compile(r"^\d{1,2}/\d{1,2}$")
HR_RE = re.compile(r"(?i)\b(?:hr|pulse|heart\s*rate)\b[:\s]*(\d{2,3})\b")
HR_LABEL_RE = re.compile(r"(?i)\b(?:hr|pulse|heart\s*rate)\b")
PLAIN_HR_RE = re.compile(r"^\d{2,3}$")
FALLBACK_BP_RE = re.compile(r"(?i)\b(?:bp[:\s]*)?(\d{2,3})\s*[/\-]\s*(\d{2,3})\b")
FALLBACK_HR_RE = re.compile(r"(?i)\b(?:hr|pulse|p)\s*(\d{2,3})\b")

_FALLBACK_BIN_SIZE = 12.0
_FALLBACK_WINDOW = 5.0

HEADER_FRACTION = 0.25
HEADER_MAX_OFFSET = 24.0

@dataclass(slots=True)
class SpanData:
    text: str
    normalized: str
    bbox: Tuple[float, float, float, float]
    center_x: float
    center_y: float
    width: float
    height: float
    line_index: int

VitalsResult = Dict[str, Optional[Union[str, int]]]


def parse_bp_token(text: str) -> Optional[str]:
    """Return ``SBP/DBP`` if ``text`` contains a blood pressure reading."""

    if not text:
        return None
    normalized = _normalize_token(text)
    match = BP_RE.search(normalized)
    if match:
        systolic, diastolic = match.groups()
        return f"{int(systolic)}/{int(diastolic)}"

    collapsed = normalized.replace(" ", "")
    if "/" in collapsed:
        parts = collapsed.split("/")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            return f"{int(parts[0])}/{int(parts[1])}"
    return None


def parse_hr_token(text: str) -> Optional[int]:
    """Return an integer heart-rate value discovered in ``text``."""

    if not text:
        return None

    normalized = _normalize_token(text)
    match = HR_RE.search(normalized)
    if match:
        try:
            value = int(match.group(1))
        except ValueError:
            return None
        if 30 <= value <= 220:
            return value
    return None


def extract_vitals_in_band(
    page: "fitz.Page",
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    *,
    allow_plain_hr: bool = False,
    dose_hint: Optional[str] = None,
    dose_bands: Optional[Dict[str, Tuple[float, float]]] = None,
) -> VitalsResult:
    """Return BP/HR vitals found within the provided rectangle."""

    if fitz is None:
        return {"bp": None, "hr": None}

    band_x0 = min(x0, x1)
    band_x1 = max(x0, x1)
    nx0, ny0, nx1, ny1 = normalize_rect((x0, y0, x1, y1))
    rect = fitz.Rect(nx0, ny0, nx1, ny1)
    try:
        text = page.get_text("dict", clip=rect)
    except RuntimeError:
        return {"bp": None, "hr": None}

    clip_rect = (nx0, ny0, nx1, ny1)
    clip_height = max(0.0, ny1 - ny0)
    header_cutoff = ny0 + min(HEADER_MAX_OFFSET, clip_height * HEADER_FRACTION)

    fragments: List[str] = []
    span_list: List[SpanData] = []
    line_index = 0
    for block in text.get("blocks", []):
        for line in block.get("lines", []):
            span_texts: List[str] = []
            for span in line.get("spans", []):
                raw_text = span.get("text")
                bbox = span.get("bbox")
                if not raw_text or not bbox:
                    continue
                normalized_bbox = normalize_rect(tuple(map(float, bbox)))
                span_texts.append(str(raw_text))
                span_list.append(_make_span_data(str(raw_text), normalized_bbox, line_index))
            if span_texts:
                fragments.append("".join(span_texts))
            line_index += 1

    combined = "\n".join(fragments)
    bp_value = _select_bp_value(span_list, clip_rect)

    if bp_value is None and combined:
        fallback_bp = parse_bp_token(combined)
        if fallback_bp and _is_plausible_bp_value(fallback_bp):
            bp_value = fallback_bp

    if bp_value is None:
        for fragment in fragments:
            candidate = parse_bp_token(fragment)
            if candidate and _is_plausible_bp_value(candidate):
                bp_value = candidate
                break

    hr_value = _select_hr_value(span_list, allow_plain_hr)

    if hr_value is None:
        hr_value = parse_hr_token(combined)

    if hr_value is None and allow_plain_hr:
        for fragment in fragments:
            hr_value = _parse_plain_hr_fragment(fragment)
            if hr_value is not None:
                break

    fallback_rows: List[Dict[str, object]] = []
    fallback_assignments: Dict[str, Dict[str, object]] = {}
    fallback_slot_clusters: Dict[str, object] = {}
    selected_row: Optional[Dict[str, object]] = None
    needs_fallback = (bp_value is None or hr_value is None)
    normalized_dose_bands = _normalize_dose_bands(dose_bands)

    if needs_fallback:
        header_bounds = (ny0, header_cutoff)
        fallback_rows = extract_vitals_in_band_fallback(page, band_x0, band_x1, header_bounds)
        slot_cluster_map: Dict[str, object] = {}
        if fallback_rows:
            if normalized_dose_bands:
                slot_cluster_map = attach_clusters_to_slots(fallback_rows, normalized_dose_bands)
                fallback_slot_clusters = slot_cluster_map
                fallback_assignments = _assign_fallback_candidates(
                    fallback_rows,
                    normalized_dose_bands,
                )
            target_row: Optional[Dict[str, object]] = None
            normalized_hint = dose_hint.upper() if dose_hint else None
            cluster_candidate: Optional[Dict[str, object]] = None
            if normalized_hint and slot_cluster_map:
                candidate = slot_cluster_map.get(normalized_hint)
                if isinstance(candidate, dict):
                    cluster_candidate = candidate
            if cluster_candidate:
                cluster_bp = cluster_candidate.get("bp")
                cluster_hr = cluster_candidate.get("hr")
                missing_bp = bp_value is None and isinstance(cluster_bp, str)
                missing_hr = hr_value is None and isinstance(cluster_hr, int)
                if missing_bp or missing_hr:
                    target_row = {
                        "bp": cluster_bp,
                        "hr": cluster_hr,
                        "y_mid": float(cluster_candidate.get("y", cluster_candidate.get("slot_y", 0.0))),
                        "context": "slot_cluster",
                    }
                    if "dy" in cluster_candidate:
                        target_row["dy"] = cluster_candidate["dy"]
                    if "slot_y" in cluster_candidate:
                        target_row["slot_y"] = cluster_candidate["slot_y"]
                    if normalized_hint:
                        target_row["dose"] = normalized_hint
            if target_row is None:
                if normalized_hint and fallback_assignments:
                    target_row = fallback_assignments.get(normalized_hint)
            if target_row is None:
                target_row = _select_candidate_for_range(fallback_rows, (ny0, ny1))
            if target_row:
                bp_candidate = target_row.get("bp")
                if bp_value is None and isinstance(bp_candidate, str):
                    bp_value = bp_candidate
                hr_candidate = target_row.get("hr")
                if hr_value is None and isinstance(hr_candidate, int):
                    hr_value = hr_candidate
                selected_row = dict(target_row)
                if normalized_hint:
                    selected_row.setdefault("dose", normalized_hint)
            if bp_value is None:
                first_bp = next((row for row in fallback_rows if row.get("bp")), None)
                if first_bp:
                    bp_candidate = first_bp.get("bp")
                    if isinstance(bp_candidate, str):
                        bp_value = bp_candidate
            if hr_value is None:
                first_hr = next((row for row in fallback_rows if row.get("hr") is not None), None)
                if first_hr:
                    hr_candidate = first_hr.get("hr")
                    if isinstance(hr_candidate, int):
                        hr_value = hr_candidate

    result: VitalsResult = {"bp": bp_value, "hr": hr_value}
    if fallback_rows:
        result["_fallback_rows"] = [dict(row) for row in fallback_rows]  # type: ignore[assignment]
    if fallback_assignments:
        assigned_copy: Dict[str, Dict[str, object]] = {}
        for key, value in fallback_assignments.items():
            if value is not None:
                assigned_copy[key] = dict(value)
        if assigned_copy:
            result["_fallback_assignments"] = assigned_copy  # type: ignore[assignment]
    if fallback_slot_clusters:
        cluster_copy: Dict[str, object] = {}
        for label in ("AM", "PM"):
            slot_info = fallback_slot_clusters.get(label)
            if isinstance(slot_info, dict):
                cluster_copy[label] = {
                    "bp": slot_info.get("bp"),
                    "hr": slot_info.get("hr"),
                    "y": slot_info.get("y"),
                    "slot_y": slot_info.get("slot_y"),
                    "dy": slot_info.get("dy"),
                    "tolerance": slot_info.get("tolerance"),
                    "assigned": slot_info.get("assigned", isinstance(slot_info.get("bp"), str) or isinstance(slot_info.get("hr"), int)),
                }
            elif slot_info is None:
                cluster_copy[label] = None
        unassigned = fallback_slot_clusters.get("unassigned")
        if isinstance(unassigned, list) and unassigned:
            cluster_copy["unassigned"] = [dict(row) for row in unassigned if isinstance(row, dict)]
        has_assignment = any(isinstance(cluster_copy.get(label), dict) for label in ("AM", "PM"))
        has_unassigned = bool(cluster_copy.get("unassigned"))
        if has_assignment or has_unassigned:
            result["_fallback_slot_clusters"] = cluster_copy  # type: ignore[assignment]
    if selected_row:
        result["_fallback_selected"] = dict(selected_row)  # type: ignore[assignment]

    return result


def _make_span_data(
    raw_text: str,
    bbox: Tuple[float, float, float, float],
    line_index: int,
) -> SpanData:
    normalized = _normalize_token(raw_text)
    x0, y0, x1, y1 = bbox
    width = max(0.0, x1 - x0)
    height = max(0.0, y1 - y0)
    return SpanData(
        text=raw_text,
        normalized=normalized,
        bbox=bbox,
        center_x=x0 + width / 2.0,
        center_y=y0 + height / 2.0,
        width=width,
        height=height,
        line_index=line_index,
    )


def _select_bp_value(spans: Iterable[SpanData], clip_rect: Tuple[float, float, float, float]) -> Optional[str]:
    span_list = list(spans)
    if not span_list:
        return None

    _, clip_top, _, clip_bottom = clip_rect
    clip_height = max(0.0, clip_bottom - clip_top)
    header_cutoff = clip_top + min(HEADER_MAX_OFFSET, clip_height * HEADER_FRACTION)

    candidates: List[Tuple[float, str]] = []
    seen: set[str] = set()

    for span in span_list:
        if not span.normalized:
            continue

        direct = parse_bp_token(span.normalized)
        if direct:
            sbp, dbp = _split_bp(direct)
            if (
                sbp is not None
                and dbp is not None
                and not _reject_header_date(span.normalized, sbp, dbp, span.center_y, header_cutoff)
                and _bp_plausible(sbp, dbp, span.center_y, header_cutoff)
            ):
                if direct not in seen:
                    candidates.append((span.center_y, direct))
                    seen.add(direct)

        stitched = _extract_stitched_bp(span, span_list, header_cutoff, seen)
        if stitched:
            candidates.extend(stitched)

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]


def _select_hr_value(span_list: Iterable[SpanData], allow_plain_hr: bool) -> Optional[int]:
    spans = list(span_list)
    if not spans:
        return None

    for index, span in enumerate(spans):
        value = _hr_from_span(span)
        if value is not None:
            return value
        if _is_hr_label_span(span):
            neighbor_value = _hr_from_neighbor_span(spans, index)
            if neighbor_value is not None:
                return neighbor_value

    if allow_plain_hr:
        for span in spans:
            value = _plain_hr_from_span(span)
            if value is not None:
                return value
    return None


def _hr_from_span(span: SpanData) -> Optional[int]:
    match = HR_RE.search(span.normalized)
    if not match:
        return None
    try:
        value = int(match.group(1))
    except ValueError:
        return None
    if 30 <= value <= 220:
        return value
    return None


def _is_hr_label_span(span: SpanData) -> bool:
    if not span.normalized:
        return False
    if not HR_LABEL_RE.search(span.normalized):
        return False
    # Already handled when digits reside in same span.
    return _hr_from_span(span) is None


def _hr_from_neighbor_span(spans: List[SpanData], index: int) -> Optional[int]:
    label = spans[index]
    for candidate in spans[index + 1 :]:
        # Stop once we move beyond the current text line.
        if candidate.line_index > label.line_index + 0:
            break
        if candidate.line_index != label.line_index:
            continue

        if candidate.bbox[0] + 0.5 < label.bbox[0]:
            continue

        x_gap = max(0.0, candidate.bbox[0] - label.bbox[2])
        if x_gap > 36.0:
            break

        value = _plain_hr_from_span(candidate)
        if value is not None:
            return value

        if candidate.normalized.strip() in {":", "-", ""}:
            continue
    return None


def _plain_hr_from_span(span: SpanData) -> Optional[int]:
    text = span.normalized
    if not text or ":" in text or "/" in text:
        return None
    match = PLAIN_HR_RE.fullmatch(text)
    if not match:
        return None
    try:
        value = int(match.group(0))
    except ValueError:
        return None
    if 30 <= value <= 220:
        return value
    return None


def _parse_plain_hr_fragment(fragment: str) -> Optional[int]:
    normalized = _normalize_token(fragment)
    if not normalized or ":" in normalized or "/" in normalized:
        return None
    match = PLAIN_HR_RE.fullmatch(normalized)
    if not match:
        return None
    try:
        value = int(match.group(0))
    except ValueError:
        return None
    if 30 <= value <= 220:
        return value
    return None


def _extract_stitched_bp(
    span: SpanData,
    span_list: Iterable[SpanData],
    header_cutoff: float,
    seen: set[str],
) -> List[Tuple[float, str]]:
    match = BP_PREFIX_RE.match(span.normalized)
    if not match:
        return []

    stitched: List[Tuple[float, str]] = []
    for other in span_list:
        if other is span:
            continue
        if not DIGITS_ONLY_RE.fullmatch(other.normalized):
            continue

        center_y = (span.center_y + other.center_y) / 2.0
        candidate = stitch_bp([span.normalized, other.normalized])
        if not candidate:
            continue
        sbp, dbp = _split_bp(candidate)
        if sbp is None or dbp is None:
            continue
        if not _bp_plausible(sbp, dbp, center_y, header_cutoff):
            continue
        if not _spans_aligned(span, other):
            continue

        if _reject_header_date(candidate, sbp, dbp, center_y, header_cutoff):
            continue
        if candidate in seen:
            continue
        stitched.append((center_y, candidate))
        seen.add(candidate)

    return stitched


def _spans_aligned(primary: SpanData, other: SpanData) -> bool:
    overlap_x = min(primary.bbox[2], other.bbox[2]) - max(primary.bbox[0], other.bbox[0])
    x_gap = 0.0 if overlap_x >= 0.0 else abs(overlap_x)
    if x_gap > 18.0:
        return False

    overlap_y = min(primary.bbox[3], other.bbox[3]) - max(primary.bbox[1], other.bbox[1])
    min_height = min(primary.height, other.height)
    if min_height <= 0.0 or overlap_y <= 0.0:
        return False
    return overlap_y / min_height >= 0.4


def _split_bp(value: str) -> Tuple[Optional[int], Optional[int]]:
    parts = value.split("/", 1)
    if len(parts) != 2:
        return (None, None)
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return (None, None)


def _bp_plausible(sbp: int, dbp: int, center_y: float, header_cutoff: float) -> bool:
    if sbp < 70 or dbp < 30:
        return False
    if sbp <= 31 and dbp <= 31 and center_y <= header_cutoff:
        return False
    return True


def _reject_header_date(
    text: str,
    sbp: int,
    dbp: int,
    center_y: float,
    header_cutoff: float,
) -> bool:
    if center_y > header_cutoff:
        return False
    if sbp > 31 or dbp > 31:
        return False
    compact = text.replace(" ", "")
    return bool(DATE_LIKE_RE.fullmatch(compact))


def _is_plausible_bp_value(value: str) -> bool:
    sbp, dbp = _split_bp(value)
    if sbp is None or dbp is None:
        return False
    if sbp <= 31 and dbp <= 31:
        return False
    if sbp < 70 or dbp < 30:
        return False
    return True


def extract_vitals_in_band_fallback(
    page: "fitz.Page",
    x0: float,
    x1: float,
    header_y_bounds: Tuple[float, float],
) -> List[Dict[str, object]]:
    """Column-centric vitals fallback when label detection fails."""

    try:
        text = page.get_text("dict")
    except RuntimeError:
        return []

    min_x = min(x0, x1)
    max_x = max(x0, x1)
    header_top, header_bottom = sorted(header_y_bounds)

    spans: List[Dict[str, object]] = []
    for block in text.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                raw_text = span.get("text")
                bbox = span.get("bbox")
                if not raw_text or not bbox:
                    continue
                sx0, sy0, sx1, sy1 = map(float, bbox)
                if sx1 < min_x or sx0 > max_x:
                    continue
                stripped = str(raw_text).strip()
                if not stripped:
                    continue
                y_mid = (sy0 + sy1) / 2.0
                spans.append(
                    {
                        "text": stripped,
                        "normalized": _normalize_token(stripped),
                        "bbox": (sx0, sy0, sx1, sy1),
                        "y_mid": y_mid,
                    }
                )

    if not spans:
        return []

    cluster_map: Dict[int, List[Dict[str, object]]] = {}
    points: List[float] = []
    for span in spans:
        try:
            y_mid = float(span["y_mid"])
        except (KeyError, TypeError, ValueError):
            continue
        bin_index = int(round(y_mid / _FALLBACK_BIN_SIZE))
        cluster_map.setdefault(bin_index, []).append(span)
        points.append(y_mid)

    cluster_centers = y_cluster(points, int(round(_FALLBACK_BIN_SIZE)))
    used_bins: set[int] = set()
    clusters: List[Tuple[float, List[Dict[str, object]]]] = []
    for center in cluster_centers:
        bin_index = int(round(center / _FALLBACK_BIN_SIZE))
        if bin_index in used_bins:
            continue
        items = cluster_map.get(bin_index)
        if not items:
            continue
        clusters.append((center, items))
        used_bins.add(bin_index)

    for bin_index, items in cluster_map.items():
        if bin_index in used_bins or not items:
            continue
        try:
            center = sum(float(item["y_mid"]) for item in items) / len(items)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            continue
        clusters.append((center, items))

    clusters.sort(key=lambda item: item[0])

    candidates: List[Dict[str, object]] = []
    for center, items in clusters:
        window_spans = [span for span in items if abs(float(span["y_mid"]) - center) <= _FALLBACK_WINDOW]
        if not window_spans:
            window_spans = items

        window_spans.sort(
            key=lambda span: (float(span["y_mid"]), float(span["bbox"][0]))  # type: ignore[index]
        )
        combined_text = " ".join(span["text"] for span in window_spans if span["text"])
        normalized_line = _normalize_token(combined_text)

        bp_value = _fallback_bp_from_spans(window_spans, header_top, header_bottom)
        if bp_value is None and normalized_line:
            bp_value = _fallback_bp_from_text(normalized_line, window_spans, header_top, header_bottom)

        hr_value = _fallback_hr_from_spans(window_spans)
        if hr_value is None and normalized_line:
            hr_value = _fallback_hr_from_text(normalized_line)

        if bp_value is None and hr_value is None:
            continue

        candidates.append(
            {
                "y_mid": center,
                "bp": bp_value,
                "hr": hr_value,
                "text": normalized_line or combined_text,
            }
        )
        if len(candidates) >= 2:
            break

    return candidates


def attach_clusters_to_slots(
    clusters: Iterable[Dict[str, object]],
    slot_bands: Dict[str, Tuple[float, float]],
    line_height_px: float = 12.0,
    extra_tolerance_px: float = 8.0,
) -> Dict[str, object]:
    normalized_bands = _normalize_dose_bands(slot_bands)
    result: Dict[str, object] = {"AM": None, "PM": None, "unassigned": []}
    for extra_label in normalized_bands:
        if extra_label not in result:
            result[extra_label] = None

    cluster_list: List[Dict[str, object]] = []
    for cluster in clusters or []:
        if not isinstance(cluster, dict):
            continue
        cluster_copy = dict(cluster)
        y_mid = cluster_copy.get("y_mid")
        try:
            y_value = float(y_mid)
        except (TypeError, ValueError):
            continue
        cluster_copy["y_mid"] = y_value
        cluster_list.append(cluster_copy)

    if not cluster_list or not normalized_bands:
        return result

    slot_entries = sorted(
        normalized_bands.items(),
        key=lambda item: (item[1][0] + item[1][1]) / 2.0,
    )
    used_indices: set[int] = set()
    base_line_height = max(0.0, float(line_height_px))
    extra_tolerance = max(0.0, float(extra_tolerance_px))

    for slot_label, bounds in slot_entries:
        top, bottom = bounds
        slot_top = min(top, bottom)
        slot_bottom = max(top, bottom)
        slot_center = (slot_top + slot_bottom) / 2.0
        slot_half_height = (slot_bottom - slot_top) / 2.0
        tolerance = max(slot_half_height, base_line_height) + extra_tolerance

        best_index: Optional[int] = None
        best_delta = float("inf")
        nearest_index: Optional[int] = None
        nearest_delta = float("inf")
        for index, cluster in enumerate(cluster_list):
            if index in used_indices:
                continue
            bp_value = cluster.get("bp")
            cluster_center = float(cluster.get("y_mid", slot_center))
            delta = abs(cluster_center - slot_center)
            if delta < nearest_delta - 1e-6:
                nearest_index = index
                nearest_delta = delta
            if not bp_value:
                continue
            if delta > tolerance:
                continue
            if delta < best_delta - 1e-6:
                best_index = index
                best_delta = delta

        target_index = best_index if best_index is not None else nearest_index
        if target_index is None:
            continue

        cluster = cluster_list[target_index]
        cluster_center = float(cluster.get("y_mid", slot_center))
        effective_delta = best_delta if best_index is not None else nearest_delta
        assigned_flag = best_index is not None
        result_entry = {
            "bp": cluster.get("bp"),
            "hr": cluster.get("hr"),
            "y": cluster_center,
            "slot_y": slot_center,
            "dy": effective_delta if effective_delta != float("inf") else abs(cluster_center - slot_center),
            "tolerance": tolerance,
            "assigned": assigned_flag,
        }
        result[slot_label] = {
            key: value
            for key, value in result_entry.items()
            if value is not None or key in {"assigned", "tolerance", "slot_y", "dy"}
        }
        if best_index is not None:
            used_indices.add(best_index)

    unassigned: List[Dict[str, object]] = []
    for index, cluster in enumerate(cluster_list):
        if index in used_indices:
            continue
        unassigned.append(dict(cluster))
    result["unassigned"] = unassigned
    return result


def _normalize_dose_bands(
    dose_bands: Optional[Dict[str, Tuple[float, float]]]
) -> Dict[str, Tuple[float, float]]:
    if not dose_bands:
        return {}
    normalized: Dict[str, Tuple[float, float]] = {}
    for key, bounds in dose_bands.items():
        if bounds is None:
            continue
        top, bottom = bounds
        if bottom < top:
            top, bottom = bottom, top
        normalized[key.upper()] = (top, bottom)
    return normalized


def _assign_fallback_candidates(
    candidates: List[Dict[str, object]],
    dose_bands: Dict[str, Tuple[float, float]],
) -> Dict[str, Dict[str, object]]:
    assignments: Dict[str, Dict[str, object]] = {}
    if not candidates or not dose_bands:
        return assignments

    ordered_bands = sorted(dose_bands.items(), key=lambda item: item[1][0])
    ordered_candidates = sorted(candidates, key=lambda row: float(row.get("y_mid", 0.0)))
    used_rows: set[int] = set()

    for candidate in ordered_candidates:
        y_mid = float(candidate.get("y_mid", 0.0))
        for label, (top, bottom) in ordered_bands:
            if label in assignments:
                continue
            if top <= y_mid <= bottom:
                assignments[label] = candidate
                used_rows.add(id(candidate))
                break

    if len(assignments) == len(dose_bands):
        return assignments

    for label, bounds in ordered_bands:
        if label in assignments:
            continue
        remaining = [row for row in ordered_candidates if id(row) not in used_rows]
        if not remaining:
            break
        center = (bounds[0] + bounds[1]) / 2.0
        closest = min(remaining, key=lambda row: abs(float(row.get("y_mid", 0.0)) - center))
        assignments[label] = closest
        used_rows.add(id(closest))

    return assignments


def _select_candidate_for_range(
    candidates: List[Dict[str, object]],
    bounds: Tuple[float, float],
) -> Optional[Dict[str, object]]:
    if not candidates:
        return None

    top, bottom = sorted(bounds)
    in_range = [
        row
        for row in candidates
        if top <= float(row.get("y_mid", 0.0)) <= bottom and (row.get("bp") or row.get("hr") is not None)
    ]
    if in_range:
        return in_range[0]

    fallback = [
        row for row in candidates if top <= float(row.get("y_mid", 0.0)) <= bottom
    ]
    if fallback:
        return fallback[0]

    prioritized = [row for row in candidates if row.get("bp") or row.get("hr") is not None]
    if prioritized:
        return prioritized[0]

    return candidates[0]


def _fallback_bp_from_spans(
    spans: Iterable[Dict[str, object]],
    header_top: float,
    header_bottom: float,
) -> Optional[str]:
    for span in spans:
        normalized = span.get("normalized")
        if not isinstance(normalized, str):
            continue
        match = FALLBACK_BP_RE.search(normalized)
        if not match:
            continue
        try:
            sbp = int(match.group(1))
            dbp = int(match.group(2))
        except ValueError:
            continue
        if sbp < 70 or dbp < 30:
            continue
        bbox = span.get("bbox")
        if isinstance(bbox, tuple) and _span_overlaps_header(bbox, header_top, header_bottom):
            continue
        return f"{sbp}/{dbp}"
    return None


def _fallback_bp_from_text(
    text: str,
    spans: Iterable[Dict[str, object]],
    header_top: float,
    header_bottom: float,
) -> Optional[str]:
    match = FALLBACK_BP_RE.search(text)
    if not match:
        return None
    try:
        sbp = int(match.group(1))
        dbp = int(match.group(2))
    except ValueError:
        return None
    if sbp < 70 or dbp < 30:
        return None
    if any(
        _span_overlaps_header(span.get("bbox"), header_top, header_bottom)
        for span in spans
    ):
        return None
    return f"{sbp}/{dbp}"


def _fallback_hr_from_spans(spans: Iterable[Dict[str, object]]) -> Optional[int]:
    for span in spans:
        normalized = span.get("normalized")
        if not isinstance(normalized, str):
            continue
        match = FALLBACK_HR_RE.search(normalized)
        if not match:
            continue
        try:
            value = int(match.group(1))
        except ValueError:
            continue
        if 30 <= value <= 220:
            return value
    return None


def _fallback_hr_from_text(text: str) -> Optional[int]:
    match = FALLBACK_HR_RE.search(text)
    if not match:
        return None
    try:
        value = int(match.group(1))
    except ValueError:
        return None
    if 30 <= value <= 220:
        return value
    return None


def _span_overlaps_header(
    bbox: Optional[Tuple[float, float, float, float]],
    header_top: float,
    header_bottom: float,
) -> bool:
    if bbox is None:
        return False
    y0 = min(bbox[1], bbox[3])
    y1 = max(bbox[1], bbox[3])
    top = min(header_top, header_bottom)
    bottom = max(header_top, header_bottom)
    return not (y1 < top or y0 > bottom)


def _normalize_token(value: str) -> str:
    replaced = value.replace("\n", " ").replace("\r", " ").strip()
    compressed = " ".join(replaced.split())
    return compressed
