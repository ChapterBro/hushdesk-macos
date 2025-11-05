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

_LEFT_GUTTER_FRACTION = 0.25
_LEFT_GUTTER_ABSOLUTE = 96.0  # 1.33 inch
_ROW_CLUSTER_TOLERANCE = 4.0
_MIN_BAND_HALF_HEIGHT = 6.0

_BP_LABEL_RE = re.compile(r"(?i)^\s*B\s*P\b")
_HR_LABEL_RE = re.compile(r"(?i)^\s*(?:HR|PULSE)\b")
_AM_LABEL_RE = re.compile(r"(?i)^\s*A\.?\s*M\.?\b")
_PM_LABEL_RE = re.compile(r"(?i)^\s*P\.?\s*M\.?\b")


@dataclass(slots=True)
class RowBands:
    """Vertical band coordinates for a single medication block."""

    bp: Optional[Tuple[float, float]] = None
    hr: Optional[Tuple[float, float]] = None
    am: Optional[Tuple[float, float]] = None
    pm: Optional[Tuple[float, float]] = None


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

    width = max(0.0, x1 - x0)
    left_gutter = x0 + min(_LEFT_GUTTER_ABSOLUTE, width * _LEFT_GUTTER_FRACTION)

    labels: Dict[str, List[LabelBox]] = {"bp": [], "hr": [], "am": [], "pm": []}
    for span_bbox, raw_text in _iter_spans_within(text, block_bbox):
        span_x0, _, span_x1, _ = span_bbox
        if span_x0 > left_gutter or span_x1 < x0:
            continue

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

    return RowBands(
        bp=row_bands["bp"],
        hr=row_bands["hr"],
        am=row_bands["am"],
        pm=row_bands["pm"],
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


def _box_center(box: LabelBox) -> float:
    return (box[1] + box[3]) / 2.0


def _cluster_center(cluster: List[LabelBox]) -> float:
    return sum(_box_center(box) for box in cluster) / len(cluster)
