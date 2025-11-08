"""Sprint 4: SBP stitch + Pulse extraction with QA overlays."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .mar_header import audit_date_from_filename, band_for_date
from .mar_tracks import TrackSpec, find_time_rows, locate_vitals_page
from .mar_tokens import VitalHit, locate_pulse_hit, stitch_sbp_hits
from .mupdf_canon import CanonPage, CanonWord, iter_canon_pages
from .qa_overlay import QAHighlights, VitalMark, draw_overlay

Rect = Tuple[float, float, float, float]
_MAX_BAND_WIDTH = 240.0


class DependencyError(RuntimeError):
    """Raised when Sprint-3 prerequisites are missing."""


@dataclass(slots=True)
class SprintContext:
    """Inputs required to extract SBP / Pulse hits."""

    pdf_path: Path
    audit_date: date
    vitals_page: int  # 1-based
    band: Tuple[float, float]
    page: CanonPage
    tracks: List[TrackSpec]


@dataclass(slots=True)
class HitCollection:
    """Container for SBP and Pulse hits."""

    sbp_hits: List[VitalHit]
    pulse_hits: List[VitalHit]

    @property
    def sbp_count(self) -> int:
        return len(self.sbp_hits)

    @property
    def pulse_count(self) -> int:
        return len(self.pulse_hits)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(argv) if argv is not None else sys.argv

    if len(args) > 2:
        print("Usage: python -m hushdesk.pdf.mar_hits [pdf-path]")
        print("HITS_MISS page=?")
        return 1

    pdf_override = Path(args[1]).expanduser() if len(args) == 2 else None

    try:
        context, hits = _build_context(pdf_override)
    except DependencyError:
        _render_empty_overlay(pdf_override)
        print("DEPENDENCY_MISS sprint=4")
        return 2

    overlay_path = _render_hits_overlay(context, hits)

    if hits.sbp_count == 0:
        print(f"SBP_MISS page={context.vitals_page}")
        return 1

    _update_next(context, hits, overlay_path)
    _update_status(context, hits, overlay_path)
    print(f"HITS_OK page={context.vitals_page} sbp_hits={hits.sbp_count} pulse_hits={hits.pulse_count}")
    return 0


def _build_context(pdf_override: Optional[Path]) -> Tuple[SprintContext, HitCollection]:
    status = _load_status()
    pdf_path = _resolve_pdf_path(status, pdf_override)
    pages = list(iter_canon_pages(pdf_path))
    if not pages:
        raise DependencyError("No pages found in PDF")

    audit_dt = _resolve_audit_date(status, pdf_path)
    vitals_page = _resolve_vitals_page(status, pages, audit_dt)
    if vitals_page is None:
        raise DependencyError("Missing vitals page")

    band = _resolve_band(status, pages, audit_dt, vitals_page)
    if band is None:
        raise DependencyError("Missing audit column band")

    context = _context_from_page(pdf_path, pages, vitals_page - 1, band, audit_dt)
    hits = _extract_hits(context)
    if hits.sbp_count > 0:
        return context, hits

    alternate = _find_context_with_hits(
        pdf_path,
        pages,
        audit_dt,
        exclude_index=vitals_page - 1,
        fallback_band=band,
    )
    if alternate is not None:
        return alternate

    return context, hits


def _context_from_page(
    pdf_path: Path,
    pages: Sequence[CanonPage],
    page_index: int,
    band: Tuple[float, float],
    audit_dt: date,
) -> SprintContext:
    if not (0 <= page_index < len(pages)):
        raise DependencyError("Vitals page index out of range")

    page = pages[page_index]
    specs = find_time_rows(page)
    tracks = _dedupe_specs(specs)
    if not tracks:
        raise DependencyError("No track specifications available")

    return SprintContext(
        pdf_path=pdf_path,
        audit_date=audit_dt,
        vitals_page=page_index + 1,
        band=band,
        page=page,
        tracks=tracks,
    )


def _dedupe_specs(specs: Sequence[TrackSpec]) -> List[TrackSpec]:
    seen: set[Tuple[str, int, int]] = set()
    unique: List[TrackSpec] = []
    for spec in specs:
        key = (
            spec.normalized_label,
            int(round(spec.track_y0)),
            int(round(spec.track_y1)),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(spec)
    return unique


def _find_context_with_hits(
    pdf_path: Path,
    pages: Sequence[CanonPage],
    audit_dt: date,
    *,
    exclude_index: Optional[int],
    fallback_band: Optional[Tuple[float, float]],
) -> Optional[Tuple[SprintContext, HitCollection]]:
    for index, page in enumerate(pages):
        if exclude_index is not None and index == exclude_index:
            continue
        band = band_for_date(page, audit_dt)
        if not band or abs(band[1] - band[0]) > _MAX_BAND_WIDTH:
            if fallback_band is None:
                continue
            band = fallback_band
        if abs(band[1] - band[0]) > _MAX_BAND_WIDTH:
            continue
        try:
            context = _context_from_page(pdf_path, pages, index, band, audit_dt)
        except DependencyError:
            continue
        hits = _extract_hits(context)
        if hits.sbp_count > 0:
            return (context, hits)
    return None


def _load_status() -> Dict[str, object]:
    status_path = Path("STATUS.json")
    if not status_path.exists():
        return {}
    try:
        with status_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}


def _resolve_pdf_path(status: Dict[str, object], override: Optional[Path]) -> Path:
    if override:
        if not override.exists():
            raise DependencyError(f"PDF not found: {override}")
        return override

    pdf_value = status.get("pdf")
    if isinstance(pdf_value, str):
        pdf_path = Path(pdf_value).expanduser()
        if pdf_path.exists():
            return pdf_path

    raise DependencyError("PDF path unavailable")


def _resolve_audit_date(status: Dict[str, object], pdf_path: Path) -> date:
    value = status.get("audit_date")
    if isinstance(value, str):
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue

    try:
        detected, _ = audit_date_from_filename(pdf_path)
    except ValueError as exc:
        raise DependencyError(str(exc)) from exc
    return detected.date()


def _resolve_vitals_page(status: Dict[str, object], pages: Sequence[CanonPage], audit_dt: date) -> Optional[int]:
    value = status.get("vitals_page")
    if isinstance(value, int) and 1 <= value <= len(pages):
        return value

    summary = locate_vitals_page(pages, audit_dt)
    if summary is None:
        return None
    return summary.page_index + 1


def _resolve_band(
    status: Dict[str, object],
    pages: Sequence[CanonPage],
    audit_dt: date,
    vitals_page: int,
) -> Optional[Tuple[float, float]]:
    raw_band = status.get("band")
    if isinstance(raw_band, (list, tuple)) and len(raw_band) >= 2:
        try:
            x0 = float(raw_band[0])
            x1 = float(raw_band[1])
            if abs(x1 - x0) <= _MAX_BAND_WIDTH:
                return (x0, x1)
        except (TypeError, ValueError):
            pass

    page = pages[vitals_page - 1]
    band = band_for_date(page, audit_dt)
    if band:
        if abs(band[1] - band[0]) <= _MAX_BAND_WIDTH:
            return band
    summary = locate_vitals_page(pages, audit_dt)
    if summary:
        if abs(summary.band[1] - summary.band[0]) <= _MAX_BAND_WIDTH:
            return summary.band
    for index, candidate in enumerate(pages):
        if index == vitals_page - 1:
            continue
        alt_band = band_for_date(candidate, audit_dt)
        if alt_band and abs(alt_band[1] - alt_band[0]) <= _MAX_BAND_WIDTH:
            return alt_band
    return None


def _extract_hits(context: SprintContext) -> HitCollection:
    x0, x1 = context.band
    left, right = min(x0, x1), max(x0, x1)
    page_width = context.page.width
    page_height = context.page.height
    column_words = [
        word
        for word in context.page.words
        if left <= word.center[0] <= right
    ]

    sbp_hits: List[VitalHit] = []
    pulse_hits: List[VitalHit] = []

    for spec in context.tracks:
        bp_rect = _cell_rect(left, right, (spec.bp_y0, spec.bp_y1), page_width, page_height)
        bp_words = _words_in_rect(column_words, bp_rect)
        sbp_hits.extend(stitch_sbp_hits(bp_words, bp_rect))

        pulse_span = (spec.pulse_y0, spec.pulse_y1)
        if pulse_span[1] > pulse_span[0]:
            pulse_rect = _cell_rect(left, right, pulse_span, page_width, page_height)
            pulse_words = _words_in_rect(column_words, pulse_rect)
            pulse_hit = locate_pulse_hit(pulse_words, context.page.words, pulse_rect)
            if pulse_hit:
                pulse_hits.append(pulse_hit)

    return HitCollection(sbp_hits=sbp_hits, pulse_hits=pulse_hits)


def _cell_rect(
    x0: float,
    x1: float,
    band: Tuple[float, float],
    page_width: float,
    page_height: float,
) -> Rect:
    left = max(0.0, min(page_width, min(x0, x1)))
    right = max(0.0, min(page_width, max(x0, x1)))
    top = max(0.0, min(page_height, min(band[0], band[1])))
    bottom = max(0.0, min(page_height, max(band[0], band[1])))
    if bottom < top:
        top, bottom = bottom, top
    return (left, top, right, bottom)


def _words_in_rect(words: Iterable[CanonWord], bounds: Rect) -> List[CanonWord]:
    x0, y0, x1, y1 = bounds
    selected: List[CanonWord] = []
    for word in words:
        wx0, wy0, wx1, wy1 = word.bbox
        if wx1 < x0 or wx0 > x1:
            continue
        if wy1 < y0 or wy0 > y1:
            continue
        selected.append(word)
    return selected


def _render_hits_overlay(context: SprintContext, hits: HitCollection) -> Path:
    left, right = sorted(context.band)
    highlights = QAHighlights(
        page_index=context.vitals_page,
        audit_band=(left, 0.0, right, context.page.height),
    )
    for hit in hits.sbp_hits:
        highlights.vitals.append(
            VitalMark(
                bbox=hit.bbox,
                label=f"SBP {hit.value}",
            )
        )
    for hit in hits.pulse_hits:
        highlights.vitals.append(
            VitalMark(
                bbox=hit.bbox,
                label=f"HR {hit.value}",
            )
        )

    output = draw_overlay(context.page.pixmap, highlights, out_dir=Path("debug"))
    target = Path("debug") / f"qa_p{context.vitals_page}_hits.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    if output != target:
        if target.exists():
            target.unlink()
        output.replace(target)
    return target


def _render_empty_overlay(pdf_override: Optional[Path]) -> None:
    status = _load_status()
    try:
        pdf_path = _resolve_pdf_path(status, pdf_override) if pdf_override else _resolve_pdf_path(status, None)
    except DependencyError:
        return

    try:
        pages = list(iter_canon_pages(Path(pdf_path)))
    except Exception:
        return
    if not pages:
        return
    page_index = 0
    vitals_page = status.get("vitals_page")
    if isinstance(vitals_page, int) and 1 <= vitals_page <= len(pages):
        page_index = vitals_page - 1
    page = pages[page_index]
    band = status.get("band") if isinstance(status.get("band"), (list, tuple)) else None
    audit_band: Optional[Rect] = None
    if isinstance(band, (list, tuple)) and len(band) >= 2:
        try:
            left, right = sorted((float(band[0]), float(band[1])))
            audit_band = (left, 0.0, right, page.height)
        except (TypeError, ValueError):
            audit_band = None
    highlights = QAHighlights(page_index=page_index + 1, audit_band=audit_band)
    output = draw_overlay(page.pixmap, highlights, out_dir=Path("debug"))
    target = Path("debug") / f"qa_p{page_index + 1}_hits.png"
    if output != target:
        if target.exists():
            target.unlink()
        output.replace(target)


def _update_next(context: SprintContext, hits: HitCollection, overlay_path: Path) -> None:
    next_path = Path("NEXT.md")
    text = (
        f"phase: hits-ok\n"
        f"vitals_page: {context.vitals_page}\n"
        f"sbp_hits: {hits.sbp_count}\n"
        f"pulse_hits: {hits.pulse_count}\n"
        f"artifacts:\n"
        f"  - {overlay_path.as_posix()}\n"
        "next_task: cell state (√/time = GIVEN; integer code = NOT-GIVEN; X = DC’D) + strict rule decisions + TXT export (headless must exit 0)\n"
    )
    next_path.write_text(text, encoding="utf-8")


def _update_status(context: SprintContext, hits: HitCollection, overlay_path: Path) -> None:
    status_path = Path("STATUS.json")
    status = _load_status()
    status["phase"] = "hits-ok"
    status["vitals_page"] = context.vitals_page
    status["band"] = [float(context.band[0]), float(context.band[1])]
    status["sbp_hits"] = hits.sbp_count
    status["pulse_hits"] = hits.pulse_count
    artifacts = [overlay_path.as_posix()]
    status["artifacts"] = artifacts
    with status_path.open("w", encoding="utf-8") as handle:
        json.dump(status, handle, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
