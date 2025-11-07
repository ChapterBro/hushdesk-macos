"""Medication block segmentation for canonical MAR pages."""

from __future__ import annotations

import io
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Sequence, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - optional dependency in automation
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFont = None  # type: ignore[assignment]

from .mar_header import detect_header
from .mupdf_canon import CanonPage, CanonWord
from .rules_normalize import RuleSet
from hushdesk.fs.exports import qa_dir

try:  # pragma: no cover - optional dependency for docs builds
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

_TITLE_UNIT_TOKENS = {"mg", "mcg", "tab", "tabs", "cap", "caps", "ml"}
_MIN_LINE_HEIGHT = 10.0
_TITLE_UPPER_RATIO = 0.65
_TITLE_MAX_LEFT_RATIO = 0.18
_TITLE_MIN_WIDTH_RATIO = 0.05
_BLOCK_TEXT_GAP_MULTIPLIER = 1.5
_PANEL_KEYWORDS = (
    "hold",
    "sbp",
    "hr",
    "pulse",
    "mg",
    "mcg",
    "tab",
    "tabs",
    "cap",
    "caps",
    "ml",
    "tablet",
    "capsule",
)


@dataclass(slots=True)
class MedBlock:
    y0: float
    y1: float
    x0: float
    x1: float
    title: str
    text: str
    rules: RuleSet = field(default_factory=RuleSet)


def block_zot(block: MedBlock, page_height: float) -> Tuple[float, float]:
    """
    Return a conservatively padded (y0, y1) clip band for ``block`` within page bounds.
    """

    if page_height <= 0.0:
        page_height = float("inf")
    y0 = max(0.0, min(block.y0, page_height))
    y1 = max(0.0, min(block.y1, page_height))
    if y1 < y0:
        y0, y1 = y1, y0
    span = max(0.0, y1 - y0)
    pad = span * 0.01 if span > 0.0 else 0.0
    return (
        max(0.0, y0 - pad),
        min(page_height, y1 + pad),
    )


@dataclass(slots=True)
class _LineSpan:
    text: str
    words: Sequence[CanonWord]
    y0: float
    y1: float
    x0: float
    x1: float


def extract_med_blocks(page: CanonPage) -> List[MedBlock]:
    """Return medication blocks detected on the left panel of ``page``."""

    panel_bounds = _panel_bounds(page)
    x0, x1 = panel_bounds
    words = [word for word in page.words if x0 <= word.center[0] <= x1]
    if not words:
        return []

    lines = _group_lines(words)
    if not lines:
        return []

    median_height = _median_line_height(lines)
    gap_threshold = median_height * _BLOCK_TEXT_GAP_MULTIPLIER

    blocks: List[MedBlock] = []
    current: List[_LineSpan] = []
    last_line: _LineSpan | None = None

    for line in lines:
        start_new = False
        if not current:
            start_new = True
        else:
            if _is_title_line(line, page.width):
                start_new = True
            elif last_line is not None and line.y0 - last_line.y1 > gap_threshold:
                start_new = True

        if start_new and current:
            blocks.append(_build_block(current, panel_bounds))
            current = []
        current.append(line)
        last_line = line

    if current:
        blocks.append(_build_block(current, panel_bounds))

    return blocks


def draw_med_blocks_debug(
    page: CanonPage,
    blocks: Sequence[MedBlock],
    out_dir: Path | str | None = None,
) -> Path | None:
    """Render medication block rectangles for QA review."""

    if fitz is None:  # pragma: no cover - defensive
        print("QA_OVERLAY_SKIP reason=PyMuPDFUnavailable")
        return None

    target_dir = Path(out_dir) if out_dir is not None else qa_dir()
    target_dir = target_dir.parent if target_dir.suffix.lower() == ".png" else target_dir

    if Image is None or ImageDraw is None or ImageFont is None:
        print("QA_OVERLAY_SKIP reason=PILUnavailable")
        return None

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        output_path = target_dir / f"qa_p{page.page_index}_blocks.png"

        image = Image.open(io.BytesIO(page.pixmap.tobytes("png"))).convert("RGBA")
        draw = ImageDraw.Draw(image, "RGBA")
        font = ImageFont.load_default()

        outline = (64, 200, 120, 220)
        fill = (64, 200, 120, 60)
        text_fill = (32, 96, 64, 255)

        for index, block in enumerate(blocks, start=1):
            rect = (block.x0, block.y0, block.x1, block.y1)
            draw.rectangle(rect, outline=outline, fill=fill, width=2)
            label = f"{index}: {block.title.strip()}"
            draw.text((block.x0 + 4, block.y0 + 2), label, fill=text_fill, font=font)

        image.save(output_path, format="PNG")
        return output_path
    except Exception as exc:
        print(f"QA_OVERLAY_SKIP reason={exc.__class__.__name__}: {exc}")
        return None


def _left_panel_limit(page: CanonPage) -> float:
    width = float(page.width)
    default_limit = width * 0.35
    detection = detect_header(page)
    if detection.tokens:
        first = min((float(token.get("x_center", width)) for token in detection.tokens), default=default_limit)
        hint = min(default_limit, first - 40.0)
    else:
        hint = default_limit
    lower = width * 0.25
    upper = width * 0.45
    return max(lower, min(hint, upper))


def _panel_bounds(page: CanonPage) -> tuple[float, float]:
    width = float(page.width)
    base_limit = _left_panel_limit(page)
    panel_width = base_limit
    orientation = _panel_side(page)
    if orientation == "right":
        left = max(0.0, width - panel_width)
        return left, width
    return 0.0, panel_width


def _panel_side(page: CanonPage) -> str:
    width = float(page.width)
    keyword_xs: List[float] = []
    for word in page.words:
        token = word.text.strip().lower()
        if not token:
            continue
        if any(token.startswith(keyword) for keyword in _PANEL_KEYWORDS):
            keyword_xs.append(float(word.center[0]))
    if keyword_xs:
        median_x = statistics.median(keyword_xs)
        if median_x > width * 0.6:
            return "right"
        if median_x < width * 0.4:
            return "left"
    return "left"


def _group_lines(words: Sequence[CanonWord]) -> List[_LineSpan]:
    ordered = sorted(words, key=lambda word: (round(word.center[1], 2), word.center[0]))
    if not ordered:
        return []

    heights = [max(word.bbox[3] - word.bbox[1], _MIN_LINE_HEIGHT) for word in ordered]
    median_height = statistics.median(heights) if heights else _MIN_LINE_HEIGHT
    tolerance = max(4.0, median_height * 0.6)

    lines: List[_LineSpan] = []
    bucket: List[CanonWord] = []
    bucket_y1 = None

    for word in ordered:
        w_y0, w_y1 = word.bbox[1], word.bbox[3]
        if not bucket:
            bucket.append(word)
            bucket_y1 = w_y1
            continue
        if bucket_y1 is not None and w_y0 <= bucket_y1 + tolerance:
            bucket.append(word)
            bucket_y1 = max(bucket_y1, w_y1)
            continue
        lines.append(_build_line(bucket))
        bucket = [word]
        bucket_y1 = w_y1

    if bucket:
        lines.append(_build_line(bucket))
    return lines


def _build_line(words: Sequence[CanonWord]) -> _LineSpan:
    ordered = sorted(words, key=lambda word: word.center[0])
    tokens = [word.text.strip() for word in ordered if word.text.strip()]
    text = " ".join(tokens)
    y0 = min(word.bbox[1] for word in ordered)
    y1 = max(word.bbox[3] for word in ordered)
    x0 = min(word.bbox[0] for word in ordered)
    x1 = max(word.bbox[2] for word in ordered)
    return _LineSpan(text=text, words=tuple(ordered), y0=y0, y1=y1, x0=x0, x1=x1)


def _median_line_height(lines: Sequence[_LineSpan]) -> float:
    heights = [line.y1 - line.y0 for line in lines if line.y1 > line.y0]
    if not heights:
        return _MIN_LINE_HEIGHT
    try:
        return float(statistics.median(heights))
    except statistics.StatisticsError:  # pragma: no cover - defensive
        return max(heights)


def _is_title_line(line: _LineSpan, page_width: float) -> bool:
    text = line.text.strip()
    if not text:
        return False

    tokens = text.split()
    if not tokens:
        return False

    letters = [char for char in text if char.isalpha()]
    upper_letters = [char for char in letters if char.isupper()]
    upper_ratio = (len(upper_letters) / len(letters)) if letters else 0.0
    has_unit = any(token.lower() in _TITLE_UNIT_TOKENS for token in tokens)
    left_bias = line.x0 <= max(page_width * _TITLE_MAX_LEFT_RATIO, 12.0)
    span_width_ratio = (line.x1 - line.x0) / page_width if page_width else 0.0

    if has_unit and upper_ratio >= _TITLE_UPPER_RATIO:
        return True
    if upper_ratio >= 0.85 and len(tokens) <= 6:
        return True
    if left_bias and has_unit and span_width_ratio >= _TITLE_MIN_WIDTH_RATIO:
        return True

    dominant_upper = sum(1 for token in tokens if token.isupper() and len(token) >= 3)
    if dominant_upper >= 2 and (has_unit or left_bias):
        return True

    return False


def _build_block(lines: Sequence[_LineSpan], bounds: tuple[float, float]) -> MedBlock:
    y0 = min(line.y0 for line in lines)
    y1 = max(line.y1 for line in lines)
    title = lines[0].text.strip()
    all_lines = [line.text.strip() for line in lines if line.text.strip()]
    text = "\n".join(all_lines)
    x0, x1 = bounds
    return MedBlock(
        y0=float(y0),
        y1=float(y1),
        x0=float(x0),
        x1=float(x1),
        title=title,
        text=text,
    )


__all__ = ["MedBlock", "block_zot", "extract_med_blocks", "draw_med_blocks_debug"]
