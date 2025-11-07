"""Row band detection helpers for MAR medication blocks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

try:  # pragma: no cover - PyMuPDF optional for unit tests
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from .geometry import normalize_rect

LabelBox = Tuple[float, float, float, float]

_ROW_CLUSTER_TOLERANCE = 4.0
_MIN_BAND_HALF_HEIGHT = 6.0

_BP_LABEL_RE = re.compile(r"(?i)^\s*B\s*P\b")
_HR_LABEL_RE = re.compile(r"(?i)^\s*(?:HR|PULSE)\b")
_AM_LABEL_RE = re.compile(r"(?i)^(?:a\.?m\.?|a\s*m\b|morning)")
_PM_LABEL_RE = re.compile(r"(?i)^(?:p\.?m\.?|p\s*m\b|evening)")
_TIME_RE = re.compile(r"\b(?:[0-1]?\d|2[0-3]):[0-5]\d\b")


@dataclass(slots=True)
class RowBands:
    """Vertical band coordinates for a single medication block."""

    bp: Optional[Tuple[float, float]] = None
    hr: Optional[Tuple[float, float]] = None
    am: Optional[Tuple[float, float]] = None
    pm: Optional[Tuple[float, float]] = None
    auto_am_pm_split: bool = False


def find_row_bands_for_block(page: "fitz.Page", block_bbox: Tuple[float, float, float, float]) -> RowBands:
    """Return semantic row bands for ``block_bbox`` on ``page``."""

    if fitz is None:
        return RowBands()

    block_bbox = normalize_rect(block_bbox)
    x0, y0, x1, y1 = block_bbox

    try:
        text = page.get_text("dict")
    except RuntimeError:
        return RowBands()

    labels: Dict[str, List[LabelBox]] = {"bp": [], "hr": [], "am": [], "pm": []}
    for span_bbox, raw_text in _iter_spans_within(text, block_bbox):
        label_key = _classify_label(raw_text)
        if label_key:
            labels[label_key].append(span_bbox)

    label_clusters: Dict[str, Optional[Tuple[float, float]]] = {
        key: _select_label_cluster(spans) for key, spans in labels.items()
    }

    centers = [
        ((cluster[0] + cluster[1]) / 2.0, key)
        for key, cluster in label_clusters.items()
        if cluster is not None
    ]
    centers.sort(key=lambda item: item[0])

    row_bands: Dict[str, Optional[Tuple[float, float]]] = {key: None for key in labels}
    for index, (center, key) in enumerate(centers):
        cluster_top, cluster_bottom = label_clusters[key]  # type: ignore[index]
        prev_center = centers[index - 1][0] if index > 0 else None
        next_center = centers[index + 1][0] if index + 1 < len(centers) else None
        row_bands[key] = _band_from_center(
            center,
            cluster_top,
            cluster_bottom,
            prev_center,
            next_center,
            y0,
            y1,
        )

    auto_am_pm_split = False
    if row_bands["am"] is None and row_bands["pm"] is None and row_bands["bp"] is not None:
        auto_split = _auto_split_am_pm(text, block_bbox, row_bands["bp"])
        if auto_split is not None:
            row_bands["am"], row_bands["pm"] = auto_split
            auto_am_pm_split = True

    return RowBands(
        bp=row_bands["bp"],
        hr=row_bands["hr"],
        am=row_bands["am"],
        pm=row_bands["pm"],
        auto_am_pm_split=auto_am_pm_split,
    )


def _iter_spans_within(text_dict: dict, bbox: Tuple[float, float, float, float]) -> Iterable[Tuple[LabelBox, str]]:
    block_x0, block_y0, block_x1, block_y1 = normalize_rect(bbox)
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                raw_text = span.get("text", "")
                span_bbox = span.get("bbox")
                if not raw_text or not span_bbox:
                    continue
                sx0, sy0, sx1, sy1 = map(float, span_bbox)
                normalized = normalize_rect((sx0, sy0, sx1, sy1))
                nx0, ny0, nx1, ny1 = normalized
                if nx1 < block_x0 or nx0 > block_x1:
                    continue
                if ny1 < block_y0 or ny0 > block_y1:
                    continue
                yield normalized, str(raw_text)


def _classify_label(text: str) -> Optional[str]:
    if _BP_LABEL_RE.match(text):
        return "bp"
    if _HR_LABEL_RE.match(text):
        return "hr"
    if _AM_LABEL_RE.match(text):
        return "am"
    if _PM_LABEL_RE.match(text):
        return "pm"
    return None


def _select_label_cluster(boxes: List[LabelBox]) -> Optional[Tuple[float, float]]:
    if not boxes:
        return None

    normalized = [normalize_rect(box) for box in boxes]
    clusters: List[List[LabelBox]] = []
    for box in sorted(normalized, key=_box_center):
        y_center = _box_center(box)
        for cluster in clusters:
            cluster_center = _cluster_center(cluster)
            if abs(y_center - cluster_center) <= _ROW_CLUSTER_TOLERANCE:
                cluster.append(box)
                break
        else:
            clusters.append([box])

    def cluster_left_edge(cluster: List[LabelBox]) -> float:
        return min(box[0] for box in cluster)

    best_cluster = min(clusters, key=cluster_left_edge)
    top = min(box[1] for box in best_cluster)
    bottom = max(box[3] for box in best_cluster)
    return top, bottom


def _band_from_center(
    center: float,
    cluster_top: float,
    cluster_bottom: float,
    prev_center: Optional[float],
    next_center: Optional[float],
    block_top: float,
    block_bottom: float,
) -> Tuple[float, float]:
    prev_gap = center - prev_center if prev_center is not None else None
    next_gap = next_center - center if next_center is not None else None

    top_half = max(_MIN_BAND_HALF_HEIGHT, (prev_gap or 0.0) / 2.0 if prev_gap else _MIN_BAND_HALF_HEIGHT)
    bottom_half = max(_MIN_BAND_HALF_HEIGHT, (next_gap or 0.0) / 2.0 if next_gap else _MIN_BAND_HALF_HEIGHT)

    top = center - top_half
    bottom = center + bottom_half

    top = min(top, cluster_top)
    bottom = max(bottom, cluster_bottom)

    top = max(block_top, top)
    bottom = min(block_bottom, bottom)

    if bottom <= top:
        top = max(block_top, center - _MIN_BAND_HALF_HEIGHT)
        bottom = min(block_bottom, center + _MIN_BAND_HALF_HEIGHT)

    if bottom <= top:
        bottom = min(block_bottom, top + _MIN_BAND_HALF_HEIGHT * 2.0)

    return top, bottom


def _auto_split_am_pm(
    text_dict: dict,
    block_bbox: Tuple[float, float, float, float],
    bp_band: Tuple[float, float],
) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    block_x0, block_y0, block_x1, block_y1 = normalize_rect(block_bbox)
    _bp_top, bp_bottom = sorted(bp_band)
    dose_top = max(block_y0, min(block_y1, bp_bottom))
    dose_bottom = block_y1
    if dose_bottom <= dose_top:
        return None

    height = dose_bottom - dose_top
    default_midpoint = dose_top + height / 2.0

    time_positions = _collect_time_positions(text_dict, (block_x0, dose_top, block_x1, dose_bottom))

    midpoint_ratio = 0.5
    if time_positions:
        above = sum(1 for pos in time_positions if pos <= default_midpoint)
        below = len(time_positions) - above
        if above and not below:
            midpoint_ratio = 0.55
        elif below and not above:
            midpoint_ratio = 0.45

    midpoint = dose_top + height * midpoint_ratio
    min_am_bottom = dose_top + _MIN_BAND_HALF_HEIGHT
    max_pm_top = dose_bottom - _MIN_BAND_HALF_HEIGHT
    midpoint = min(max(midpoint, min_am_bottom), max_pm_top)

    am_top = dose_top
    am_bottom = midpoint
    pm_top = midpoint
    pm_bottom = dose_bottom

    if am_bottom - am_top < _MIN_BAND_HALF_HEIGHT:
        am_bottom = min(dose_bottom - _MIN_BAND_HALF_HEIGHT, am_top + _MIN_BAND_HALF_HEIGHT)
        pm_top = am_bottom
    if pm_bottom - pm_top < _MIN_BAND_HALF_HEIGHT:
        pm_top = max(dose_top + _MIN_BAND_HALF_HEIGHT, pm_bottom - _MIN_BAND_HALF_HEIGHT)
        am_bottom = pm_top

    if am_bottom <= am_top or pm_bottom <= pm_top:
        return None

    return (am_top, am_bottom), (pm_top, pm_bottom)


def _collect_time_positions(
    text_dict: dict,
    bbox: Tuple[float, float, float, float],
) -> List[float]:
    x0, y0, x1, y1 = normalize_rect(bbox)
    positions: List[float] = []
    for span_bbox, raw_text in _iter_spans_within(text_dict, (x0, y0, x1, y1)):
        text = str(raw_text)
        if not text:
            continue
        if not _TIME_RE.search(text):
            continue
        pos_y = (span_bbox[1] + span_bbox[3]) / 2.0
        positions.append(pos_y)
    return positions


def _box_center(box: LabelBox) -> float:
    return (box[1] + box[3]) / 2.0


def _cluster_center(cluster: List[LabelBox]) -> float:
    return sum(_box_center(box) for box in cluster) / len(cluster)
