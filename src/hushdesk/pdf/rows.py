"""Row band detection helpers for MAR medication blocks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

try:  # pragma: no cover - PyMuPDF optional for unit tests
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

LabelBox = Tuple[float, float, float, float]

_LEFT_GUTTER_FRACTION = 0.25
_LEFT_GUTTER_ABSOLUTE = 96.0  # 1.33 inch
_ROW_CLUSTER_TOLERANCE = 4.0


@dataclass(slots=True)
class RowBands:
    """Vertical band coordinates for a single medication block."""

    bp: Optional[Tuple[float, float]] = None
    hr: Optional[Tuple[float, float]] = None
    am: Optional[Tuple[float, float]] = None
    pm: Optional[Tuple[float, float]] = None


def find_row_bands_for_block(page: "fitz.Page", block_bbox: Tuple[float, float, float, float]) -> RowBands:
    """Return semantic row bands for ``block_bbox`` on ``page``.

    The detection scans spans near the left edge of the block and clusters
    vertical positions for the ``BP``, ``Pulse``/``HR``, ``AM`` and ``PM`` labels.
    """

    if fitz is None:
        return RowBands()

    try:
        text = page.get_text("dict")
    except RuntimeError:
        return RowBands()

    x0, y0, x1, y1 = block_bbox
    width = max(0.0, x1 - x0)
    left_gutter = x0 + min(_LEFT_GUTTER_ABSOLUTE, width * _LEFT_GUTTER_FRACTION)

    labels: Dict[str, List[LabelBox]] = {"bp": [], "hr": [], "am": [], "pm": []}

    for span_bbox, raw_text in _iter_spans_within(text, block_bbox):
        span_x0, _, span_x1, _ = span_bbox
        if span_x0 > left_gutter:
            continue
        if span_x1 < x0:
            continue

        label_key = _classify_label(raw_text)
        if not label_key:
            continue
        labels[label_key].append(span_bbox)

    return RowBands(
        bp=_collapse_label_boxes(labels["bp"]),
        hr=_collapse_label_boxes(labels["hr"]),
        am=_collapse_label_boxes(labels["am"]),
        pm=_collapse_label_boxes(labels["pm"]),
    )


def _iter_spans_within(text_dict: dict, bbox: Tuple[float, float, float, float]) -> Iterable[Tuple[LabelBox, str]]:
    block_x0, block_y0, block_x1, block_y1 = bbox
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                raw_text = span.get("text", "")
                span_bbox = span.get("bbox")
                if not raw_text or not span_bbox:
                    continue
                sx0, sy0, sx1, sy1 = map(float, span_bbox)
                if sx1 < block_x0 or sx0 > block_x1:
                    continue
                if sy1 < block_y0 or sy0 > block_y1:
                    continue
                yield (sx0, sy0, sx1, sy1), str(raw_text)


def _classify_label(text: str) -> Optional[str]:
    cleaned = text.strip().lower().replace(".", "")
    if not cleaned:
        return None
    if cleaned in {"bp", "b/p"} or cleaned.startswith("bp "):
        return "bp"
    if cleaned in {"pulse", "hr", "heart rate"}:
        return "hr"
    if cleaned in {"am"}:
        return "am"
    if cleaned in {"pm"}:
        return "pm"
    return None


def _collapse_label_boxes(boxes: List[LabelBox]) -> Optional[Tuple[float, float]]:
    if not boxes:
        return None

    clusters: List[List[LabelBox]] = []
    for box in sorted(boxes, key=lambda item: (item[1] + item[3]) / 2.0):
        y_center = (box[1] + box[3]) / 2.0
        for cluster in clusters:
            cluster_center = _cluster_center(cluster)
            if abs(y_center - cluster_center) <= _ROW_CLUSTER_TOLERANCE:
                cluster.append(box)
                break
        else:
            clusters.append([box])

    # Choose the cluster whose left edge is closest to the block gutter
    def cluster_left_edge(cluster: List[LabelBox]) -> float:
        return min(box[0] for box in cluster)

    best_cluster = min(clusters, key=cluster_left_edge)
    top = min(box[1] for box in best_cluster)
    bottom = max(box[3] for box in best_cluster)
    return (top, bottom)


def _cluster_center(cluster: List[LabelBox]) -> float:
    return sum((box[1] + box[3]) / 2.0 for box in cluster) / len(cluster)
