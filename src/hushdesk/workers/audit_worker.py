"""Background worker that simulates auditing a MAR PDF."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal, Slot

try:  # pragma: no cover - optional dependency when tests run without PyMuPDF
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from hushdesk.engine.decide import decide_for_dose
from hushdesk.pdf.columns import ColumnBand, select_audit_columns
from hushdesk.pdf.dates import format_mmddyyyy, resolve_audit_date
from hushdesk.pdf.duecell import DueMark, detect_due_mark
from hushdesk.pdf.geometry import normalize_rect
from hushdesk.pdf.rows import find_row_bands_for_block
from hushdesk.pdf.vitals import extract_vitals_in_band
from hushdesk.placeholders import build_placeholder_output


logger = logging.getLogger(__name__)

ROOM_BED_RE = re.compile(r"\b\d{3}-\d\b")
RULE_PATTERN = re.compile(r"(?i)(sbp|hr|pulse)\s*([<>])\s*(\d{2,3})")
TIME_RE = re.compile(r"\b(?:[0-1]?\d|2[0-3]):[0-5]\d\b")
ROW_PADDING = 4.0


@dataclass(slots=True)
class RuleSpec:
    kind: str
    threshold: int
    description: str

    @classmethod
    def from_kwargs(cls, **kwargs: object) -> "RuleSpec":
        """Temporary adapter to smooth over legacy keyword usage."""
        if "rule_kind" in kwargs and "kind" not in kwargs:
            kwargs["kind"] = kwargs.pop("rule_kind")
        return cls(**kwargs)


class AuditWorker(QObject):
    """Worker that simulates page-by-page progress in a background thread."""

    started = Signal(str)
    progress = Signal(int, int)
    log = Signal(str)
    saved = Signal(str)
    warning = Signal(str)
    audit_date_text = Signal(str)
    summary_counts = Signal(dict)
    no_data_for_date = Signal()
    finished = Signal(Path)

    def __init__(self, input_pdf: Path, delay: float = 0.2) -> None:
        super().__init__()
        self._input_pdf = input_pdf
        self._delay = max(0.05, delay)
        self._audit_date: date | None = None

    @Slot()
    def run(self) -> None:
        self.started.emit(str(self._input_pdf))

        audit_date = resolve_audit_date(self._input_pdf)
        self._audit_date = audit_date
        label_value = f"{format_mmddyyyy(audit_date)} — Central"
        self.audit_date_text.emit(label_value)

        column_bands: List[ColumnBand] = []
        missing_headers: List[int] = []
        counters = self._empty_summary()
        doc_pages = 0
        no_data_emitted = False
        if fitz is None:
            message = "PyMuPDF is not available; skipping column band detection."
            logger.warning(message)
            self.warning.emit(message)
        elif self._input_pdf.exists():
            try:
                with fitz.open(self._input_pdf) as doc:
                    doc_pages = len(doc)
                    self.log.emit(f"Opened doc: pages={doc_pages}")
                    column_bands = select_audit_columns(
                        doc,
                        audit_date,
                        on_page_without_header=missing_headers.append,
                    )
                    self.log.emit(
                        f"Processing {len(column_bands)} band pages (of {doc_pages} total pages)"
                    )
                    for page_index in missing_headers:
                        self.log.emit(f"No header on page {page_index + 1} (skipped)")
                    for band in column_bands:
                        self.log.emit(
                            "ColumnBand page=%d x0=%.1fpt x1=%.1fpt frac=%.3f–%.3f"
                            % (band.page_index + 1, band.x0, band.x1, band.frac0, band.frac1)
                        )
                    if column_bands:
                        total_steps = len(column_bands)
                        for index, band in enumerate(column_bands, start=1):
                            time.sleep(self._delay)
                            page = doc.load_page(band.page_index)
                            band_counts = self._evaluate_column_band(page, band)
                            self._merge_counts(counters, band_counts)
                            self.progress.emit(index, total_steps)
                    else:
                        self.no_data_for_date.emit()
                        no_data_emitted = True
                        warning_message = "No data for selected date"
                        self.warning.emit(warning_message)
            except Exception as exc:  # pragma: no cover - defensive guard
                message = f"Unable to compute column bands for {self._input_pdf}: {exc}"
                logger.warning(message, exc_info=True)
                self.warning.emit(message)
        else:
            message = f"Input PDF {self._input_pdf} does not exist; skipping column band detection."
            logger.warning(message)
            self.warning.emit(message)

        output_path = self._input_pdf.with_suffix(".txt")

        logger.info("Column selection result for %s: %s", audit_date.isoformat(), column_bands)

        if not column_bands and not no_data_emitted:
            self.no_data_for_date.emit()
            no_data_emitted = True

        self.summary_counts.emit(counters)
        if self._write_placeholder(output_path):
            self.saved.emit(str(output_path))

        self.finished.emit(output_path)

    def _write_placeholder(self, output_path: Path) -> bool:
        try:
            output_path.write_text(build_placeholder_output(self._input_pdf))
            return True
        except OSError as exc:
            message = f"Unable to save placeholder TXT to {output_path}: {exc}"
            logger.warning(message)
            self.warning.emit(message)
            # Surface error handling can be added later; for now we still emit finished
            return False

    # --- Band evaluation ----------------------------------------------------

    def _evaluate_column_band(self, page: "fitz.Page", band: ColumnBand) -> Dict[str, int]:
        counts = self._empty_summary()
        try:
            text_dict = page.get_text("dict")
        except RuntimeError:
            return counts

        block_candidates = self._find_block_candidates(page, band, text_dict)
        for block_bbox, rule_text in block_candidates:
            rule_specs = self._parse_rules(rule_text)
            if not rule_specs:
                continue

            row_bands = find_row_bands_for_block(page, block_bbox)
            am_band = self._expand_band(row_bands.am, block_bbox)
            pm_band = self._expand_band(row_bands.pm, block_bbox)
            if am_band is None and pm_band is None:
                continue

            bp_band = self._expand_band(row_bands.bp, block_bbox)
            hr_band = self._expand_band(row_bands.hr, block_bbox)

            bp_value = None
            hr_value = None
            if bp_band is not None:
                bp_result = extract_vitals_in_band(page, band.x0, band.x1, *bp_band)
                bp_value = bp_result.get("bp")
            if hr_band is not None:
                hr_result = extract_vitals_in_band(page, band.x0, band.x1, *hr_band)
                hr_value = hr_result.get("hr")

            room_bed = self._find_room_bed_label(page, block_bbox) or "Unknown"

            for slot_name, slot_band in (("AM", am_band), ("PM", pm_band)):
                if slot_band is None:
                    continue

                slot_vitals = extract_vitals_in_band(page, band.x0, band.x1, *slot_band)
                slot_bp = bp_value or slot_vitals.get("bp")
                slot_hr = hr_value or slot_vitals.get("hr")
                sbp_value = self._sbp_from_bp(slot_bp)

                mark = detect_due_mark(page, band.x0, band.x1, *slot_band)
                mark_text = self._collect_text(page, band.x0, band.x1, *slot_band)
                counts["reviewed"] += 1
                if mark == DueMark.NONE:
                    self.log.emit(f"WARN — missing due mark — {room_bed} ({slot_name})")

                for rule in rule_specs:
                    vital_value: Optional[int]
                    if rule.kind.startswith("SBP"):
                        vital_value = sbp_value
                        if vital_value is None:
                            self.log.emit(
                                f"WARN — SBP missing — {room_bed} ({slot_name})"
                            )
                    else:
                        vital_value = slot_hr
                        if vital_value is None:
                            self.log.emit(
                                f"WARN — HR missing — {room_bed} ({slot_name})"
                            )

                    decision = decide_for_dose(rule.kind, rule.threshold, vital_value, mark)
                    if decision == "HELD_OK":
                        counts["held_ok"] += 1
                    elif decision == "HOLD_MISS":
                        counts["hold_miss"] += 1
                    elif decision == "COMPLIANT":
                        counts["compliant"] += 1
                    elif decision == "DCD":
                        counts["dcd"] += 1
                    elif decision == "NONE" and mark == DueMark.CODE_ALLOWED:
                        self.log.emit(
                            f"WARN — allowed code without trigger — {room_bed} ({slot_name})"
                        )

                    message = self._format_decision_log(
                        decision,
                        room_bed,
                        slot_name,
                        rule,
                        slot_bp,
                        slot_hr,
                        mark,
                        mark_text,
                    )
                    self.log.emit(message)

        return counts

    def _find_block_candidates(
        self,
        page: "fitz.Page",
        band: ColumnBand,
        text_dict: dict,
    ) -> List[Tuple[Tuple[float, float, float, float], str]]:
        candidates: List[Tuple[Tuple[float, float, float, float], str]] = []
        for block in text_dict.get("blocks", []):
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                line_text = "".join(str(span.get("text", "")) for span in spans).strip()
                if not line_text:
                    continue
                lowered = line_text.lower()
                if "hold" not in lowered:
                    continue
                if "<" not in line_text and ">" not in line_text:
                    continue
                bbox = self._line_bbox(spans)
                if bbox is None:
                    continue
                block_bbox = normalize_rect(
                    (
                        max(0.0, min(band.x0 - 120.0, bbox[0] - 12.0)),
                        max(0.0, bbox[1] - 36.0),
                        band.x1,
                        min(page.rect.height, bbox[3] + 140.0),
                    )
                )
                candidates.append((block_bbox, line_text))

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

    def _parse_rules(self, text: str) -> List[RuleSpec]:
        specs: List[RuleSpec] = []
        for match in RULE_PATTERN.finditer(text):
            raw_measure, comparator, value = match.groups()
            measure = raw_measure.upper()
            if measure == "PULSE":
                measure = "HR"
            rule_kind = f"{measure}{comparator}"
            try:
                threshold = int(value)
            except ValueError:
                continue
            specs.append(
                RuleSpec(
                    kind=rule_kind,
                    threshold=threshold,
                    description=f"Hold if {measure} {comparator} {threshold}",
                )
            )
        return specs

    @staticmethod
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
        expanded_top = max(block_top, top - ROW_PADDING)
        expanded_bottom = min(block_bottom, bottom + ROW_PADDING)
        if expanded_bottom <= expanded_top:
            return None
        return expanded_top, expanded_bottom

    @staticmethod
    def _sbp_from_bp(bp: Optional[str]) -> Optional[int]:
        if not bp:
            return None
        parts = bp.split("/")
        if not parts:
            return None
        try:
            return int(parts[0])
        except ValueError:
            return None

    def _find_room_bed_label(
        self, page: "fitz.Page", block_bbox: Tuple[float, float, float, float]
    ) -> Optional[str]:
        block_x0, block_y0, block_x1, block_y1 = normalize_rect(block_bbox)
        search_rect = fitz.Rect(
            max(0.0, block_x0 - 160.0),
            block_y0,
            block_x0,
            block_y1,
        )
        try:
            text = page.get_text("text", clip=search_rect)
        except RuntimeError:
            return None
        match = ROOM_BED_RE.search(text)
        if match:
            return match.group(0)
        return None

    def _collect_text(self, page: "fitz.Page", x0: float, x1: float, y0: float, y1: float) -> str:
        nx0, ny0, nx1, ny1 = normalize_rect((x0, y0, x1, y1))
        rect = fitz.Rect(nx0, ny0, nx1, ny1)
        try:
            return page.get_text("text", clip=rect).strip()
        except RuntimeError:
            return ""

    @staticmethod
    def _line_bbox(spans: List[dict]) -> Optional[Tuple[float, float, float, float]]:
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

    def _format_decision_log(
        self,
        decision: str,
        room_bed: str,
        slot_name: str,
        rule: RuleSpec,
        bp_value: Optional[str],
        hr_value: Optional[int],
        mark: DueMark,
        mark_text: str,
    ) -> str:
        label = self._decision_label(decision)
        detail_parts: List[str] = []

        if rule.kind.startswith("SBP"):
            if bp_value:
                detail_parts.append(f"BP {bp_value}")
            else:
                detail_parts.append("BP missing")
        else:
            if hr_value is not None:
                detail_parts.append(f"HR {hr_value}")
            else:
                detail_parts.append("HR missing")

        mark_desc = self._describe_due_mark(mark, mark_text)
        if mark_desc:
            detail_parts.append(mark_desc)

        details = "; ".join(detail_parts) if detail_parts else ""
        base = f"{label} — {room_bed} ({slot_name}) — {rule.description}"
        if details:
            return f"{base}; {details}"
        return base

    @staticmethod
    def _decision_label(decision: str) -> str:
        if decision == "NONE":
            return "INFO"
        return decision.replace("_", "-")

    @staticmethod
    def _describe_due_mark(mark: DueMark, mark_text: str) -> Optional[str]:
        if mark == DueMark.DCD:
            return "X in due cell"
        if mark == DueMark.CODE_ALLOWED:
            code_match = re.search(r"\b(\d{1,2})\b", mark_text)
            if code_match:
                return f"code {code_match.group(1)}"
            return "allowed code"
        if mark == DueMark.GIVEN_CHECK:
            return "check mark present"
        if mark == DueMark.GIVEN_TIME:
            time_match = TIME_RE.search(mark_text)
            if time_match:
                return f"time {time_match.group(0)}"
            return "time recorded"
        if mark == DueMark.NONE:
            return None
        return None

    @staticmethod
    def _empty_summary() -> Dict[str, int]:
        return {
            "reviewed": 0,
            "hold_miss": 0,
            "held_ok": 0,
            "compliant": 0,
            "dcd": 0,
        }

    @staticmethod
    def _merge_counts(target: Dict[str, int], delta: Dict[str, int]) -> None:
        for key in target:
            target[key] += int(delta.get(key, 0))
