"""QA overlay rendering using PIL on MuPDF pixmaps."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - optional dependency in headless automation
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFont = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency during docs builds
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from hushdesk.fs.exports import resolve_qa_prefix

Color = Tuple[int, int, int, int]
Rect = Tuple[float, float, float, float]

_AUDIT_FILL: Color = (32, 120, 240, 64)
_AUDIT_OUTLINE: Color = (32, 120, 240, 180)
_TIME_LINE: Color = (240, 96, 32, 200)
_VITAL_FILL: Color = (250, 240, 32, 90)
_VITAL_OUTLINE: Color = (250, 192, 0, 220)
_VITAL_TEXT: Color = (40, 40, 40, 255)


@dataclass(slots=True)
class TimeRail:
    y: float
    label: Optional[str] = None


@dataclass(slots=True)
class VitalMark:
    bbox: Rect
    label: str


@dataclass(slots=True)
class QAHighlights:
    """Container for QA overlay drawing primitives."""

    page_index: int
    audit_band: Optional[Rect] = None
    time_rails: List[TimeRail] = field(default_factory=list)
    vitals: List[VitalMark] = field(default_factory=list)


def draw_overlay(
    pixmap: "fitz.Pixmap",
    highlights: QAHighlights,
    qa_prefix: str | Path | None = None,
) -> Path | None:
    """Render QA overlays and persist them to the resolved QA directory."""

    if fitz is None:  # pragma: no cover - defensive
        print("QA_OVERLAY_SKIP reason=PyMuPDFUnavailable")
        return None

    if qa_prefix is False:  # type: ignore[comparison-overlap]
        print("QA_OVERLAY_SKIP reason=disabled")
        return None

    if Image is None or ImageDraw is None or ImageFont is None:
        print("QA_OVERLAY_SKIP reason=PILUnavailable")
        return None

    try:
        target = Path(resolve_qa_prefix(qa_prefix))
    except Exception as exc:  # pragma: no cover - defensive
        print(f"QA_OVERLAY_SKIP reason={exc.__class__.__name__}: {exc}")
        return None

    try:
        if target.suffix.lower() == ".png":
            target.parent.mkdir(parents=True, exist_ok=True)
            output_path = target
        else:
            target.mkdir(parents=True, exist_ok=True)
            output_path = target / f"qa_p{highlights.page_index}.png"

        png_bytes = pixmap.tobytes("png")
        image = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        draw = ImageDraw.Draw(image, "RGBA")
        font = ImageFont.load_default()

        if highlights.audit_band:
            _draw_audit_band(draw, highlights.audit_band)

        _draw_time_rails(draw, image.size, highlights.time_rails, highlights.audit_band)
        _draw_vitals(draw, highlights.vitals, font)

        image.save(output_path, format="PNG")
        return output_path
    except Exception as exc:
        print(f"QA_OVERLAY_SKIP reason={exc.__class__.__name__}: {exc}")
        return None


def _draw_audit_band(draw: ImageDraw.ImageDraw, rect: Rect) -> None:
    x0, y0, x1, y1 = (round(value, 1) for value in rect)
    draw.rectangle((x0, y0, x1, y1), outline=_AUDIT_OUTLINE, fill=_AUDIT_FILL, width=3)


def _draw_time_rails(
    draw: ImageDraw.ImageDraw,
    image_size: Tuple[int, int],
    rails: Sequence[TimeRail],
    audit_band: Optional[Rect],
) -> None:
    if not rails:
        return
    if audit_band:
        band_x0, _, band_x1, _ = audit_band
    else:
        band_x0, band_x1 = 0.0, float(image_size[0])

    for rail in rails:
        y = float(rail.y)
        draw.line(((band_x0, y), (band_x1, y)), fill=_TIME_LINE, width=2)
        if rail.label:
            draw.text((band_x0 + 4, y + 2), rail.label, fill=_TIME_LINE[0:3] + (255,))


def _draw_vitals(draw: ImageDraw.ImageDraw, vitals: Sequence[VitalMark], font: ImageFont.ImageFont) -> None:
    for mark in vitals:
        x0, y0, x1, y1 = mark.bbox
        draw.rectangle((x0, y0, x1, y1), outline=_VITAL_OUTLINE, fill=_VITAL_FILL, width=2)
        label_x = x0 + 4
        label_y = y0 + 2
        draw.text((label_x, label_y), mark.label, fill=_VITAL_TEXT, font=font)


__all__ = ["QAHighlights", "TimeRail", "VitalMark", "draw_overlay"]
