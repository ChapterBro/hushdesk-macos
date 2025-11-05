"""Background worker that simulates auditing a MAR PDF."""

from __future__ import annotations

import logging
import re
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal, Slot

try:  # pragma: no cover - optional dependency when tests run without PyMuPDF
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from hushdesk.engine.decide import decide_for_dose
from hushdesk.engine.rules import RuleSpec, parse_rule_text
from hushdesk.id.rooms import load_building_master, resolve_room_from_block
from hushdesk.pdf.columns import ColumnBand, select_audit_columns
from hushdesk.pdf.dates import format_mmddyyyy, resolve_audit_date
from hushdesk.pdf.duecell import DueMark, detect_due_mark
from hushdesk.pdf.geometry import normalize_rect
from hushdesk.pdf.rows import find_row_bands_for_block
from hushdesk.pdf.vitals import extract_vitals_in_band
from hushdesk.report.model import DecisionRecord
from hushdesk.report.txt_writer import write_report


logger = logging.getLogger(__name__)

DEBUG_DECISION_DETAILS = False

TIME_RE = re.compile(r"\b(?:[0-1]?\d|2[0-3]):[0-5]\d\b")
ROW_PADDING = 4.0


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
        self._building_master = load_building_master()
        self._unknown_room_debug_warned = False

    @Slot()
    def run(self) -> None:
        self.started.emit(str(self._input_pdf))

        audit_date = resolve_audit_date(self._input_pdf)
        self._audit_date = audit_date
        label_value = f"{format_mmddyyyy(audit_date)} — Central"
        audit_date_text = format_mmddyyyy(audit_date)
        label_value = f"{audit_date_text} — Central"
        self.audit_date_text.emit(label_value)

        column_bands: List[ColumnBand] = []
        missing_headers: List[int] = []
        counters = self._empty_summary()
        records: List[DecisionRecord] = []
        hall_counts: Counter[str] = Counter()
        run_notes: List[str] = []
        notes_seen: set[str] = set()
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
                            band_counts = self._evaluate_column_band(
                                page,
                                band,
                                audit_date_text,
                                self._input_pdf.name,
                                records,
                                hall_counts,
                                run_notes,
                                notes_seen,
                            )
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

        logger.info("Column selection result for %s: %s", audit_date.isoformat(), column_bands)

        if not column_bands and not no_data_emitted:
            self.no_data_for_date.emit()
            no_data_emitted = True
            self._add_note(run_notes, notes_seen, "No data for selected date")

        self.summary_counts.emit(counters)
        hall = self._resolve_report_hall(hall_counts)
        if hall == "UNKNOWN":
            self._add_note(run_notes, notes_seen, "Hall could not be resolved from room-bed tokens")
        elif hall == "MIXED":
            self._add_note(run_notes, notes_seen, "Rooms span multiple halls (mixed)")

        output_path = self._build_output_path(audit_date, hall)
        try:
            write_report(
                records,
                counters,
                audit_date_text,
                hall,
                self._input_pdf.name,
                output_path,
                run_notes,
            )
            self.saved.emit(str(output_path))
        except OSError as exc:
            message = f"Unable to save TXT to {output_path}: {exc}"
            logger.warning(message)
            self.warning.emit(message)

        self.finished.emit(output_path)

    # --- Band evaluation ----------------------------------------------------

    def _evaluate_column_band(
        self,
        page: "fitz.Page",
        band: ColumnBand,
        audit_date_text: str,
        source_basename: str,
        records: List[DecisionRecord],
        hall_counts: Counter[str],
        run_notes: List[str],
        notes_seen: set[str],
    ) -> Dict[str, int]:
        counts = self._empty_summary()
        try:
            text_dict = page.get_text("dict")
        except RuntimeError:
            return counts

        block_candidates = self._find_block_candidates(page, band, text_dict)
        for block_bbox, rule_text in block_candidates:
            rule_specs = parse_rule_text(rule_text)
            if not rule_specs:
                continue

            row_bands = find_row_bands_for_block(page, block_bbox)
            block_rect = normalize_rect(block_bbox)
            room_info, room_spans = self._resolve_room_info(text_dict, block_rect)
            if room_info:
                room_bed, hall_name = room_info
                if hall_name and hall_name.lower() != "unknown":
                    hall_counts[hall_name] += 1
            else:
                room_bed = "Unknown"
                hall_name = "Unknown"
                self.log.emit(
                    "WARN — room-bed unresolved — "
                    f"page {band.page_index + 1} y={block_rect[1]:.1f}-{block_rect[3]:.1f}"
                )
                self._add_note(
                    run_notes,
                    notes_seen,
                    f"Room not resolved for block on page {band.page_index + 1}",
                )
                if DEBUG_DECISION_DETAILS and not self._unknown_room_debug_warned:
                    snippet = self._summarize_room_spans(room_spans)
                    if snippet:
                        self.log.emit(f"WARN — room parse sample — {snippet}")
                        self._unknown_room_debug_warned = True
            split_band_used = getattr(row_bands, "auto_am_pm_split", False)
            if DEBUG_DECISION_DETAILS:
                rule_parts = ", ".join(f"{spec.kind}@{spec.threshold}" for spec in rule_specs)
                rows_desc = ", ".join(
                    [
                        f"bp={row_bands.bp}",
                        f"hr={row_bands.hr}",
                        f"am={row_bands.am}",
                        f"pm={row_bands.pm}",
                    ]
                )
                self.log.emit(
                    "DEBUG — block=(%.1f, %.1f, %.1f, %.1f); room=%s; rules=[%s]; rows=[%s]"
                    % (*block_rect, room_bed, rule_parts, rows_desc)
                )
            slot_bands = {
                "AM": self._expand_band(row_bands.am, block_rect),
                "PM": self._expand_band(row_bands.pm, block_rect),
            }
            fallback_used = False
            if not any(slot_bands.values()):
                fallback_band = self._expand_band(
                    (block_rect[1], block_rect[3]),
                    block_rect,
                )
                if fallback_band is None:
                    continue
                slot_bands = {"AM": fallback_band}
                fallback_used = True

            slot_sequence = [(name, band) for name, band in slot_bands.items() if band is not None]
            if not slot_sequence:
                continue

            bp_band = self._expand_band(row_bands.bp, block_rect)
            hr_band = self._expand_band(row_bands.hr, block_rect)

            bp_value = None
            hr_value = None
            slot_x0 = max(band.x0, block_rect[0])
            slot_x1 = block_rect[2]
            if bp_band is not None:
                bp_result = extract_vitals_in_band(page, slot_x0, slot_x1, *bp_band)
                bp_value = bp_result.get("bp")
            if hr_band is not None:
                hr_result = extract_vitals_in_band(page, slot_x0, slot_x1, *hr_band)
                hr_value = hr_result.get("hr")

            if split_band_used:
                self.log.emit(
                    f"WARN — AM/PM labels missing, using 50/50 split for block {room_bed}"
                )
            elif fallback_used:
                self.log.emit(
                    f"WARN — fallback slot band used — {room_bed}"
                )

            for slot_name, slot_band in slot_sequence:
                slot_label = slot_name
                if split_band_used:
                    slot_label = f"{slot_name} (split)"
                elif fallback_used:
                    slot_label = f"{slot_name} (fallback)"

                slot_vitals = extract_vitals_in_band(page, slot_x0, slot_x1, *slot_band)
                slot_bp = bp_value or slot_vitals.get("bp")
                slot_hr = hr_value or slot_vitals.get("hr")
                sbp_value = self._sbp_from_bp(slot_bp)

                mark = detect_due_mark(page, slot_x0, slot_x1, *slot_band)
                mark_text = self._collect_text(page, slot_x0, slot_x1, *slot_band)

                if DEBUG_DECISION_DETAILS:
                    self._emit_debug_bundle(
                        block_rect,
                        room_bed,
                        hall_name,
                        rule_specs,
                        row_bands,
                        slot_label,
                        mark,
                        mark_text,
                        slot_bp,
                        slot_hr,
                        split_band_used,
                        fallback_used,
                    )
                counts["reviewed"] += 1
                if mark == DueMark.NONE:
                    self.log.emit(f"WARN — missing due mark — {room_bed} ({slot_label})")

                record_notes: List[str] = []
                if split_band_used:
                    record_notes.append("split")
                elif fallback_used:
                    record_notes.append("fallback")

                dcd_counted = False
                for rule in rule_specs:
                    vital_value: Optional[int]
                    if rule.kind.startswith("SBP"):
                        vital_value = sbp_value
                        if vital_value is None:
                            self.log.emit(
                                f"WARN — SBP missing — {room_bed} ({slot_label})"
                            )
                            self._add_note(
                                run_notes,
                                notes_seen,
                                f"Vitals missing (unexpected) — {room_bed} ({slot_label})",
                            )
                            if "vitals missing" not in record_notes:
                                record_notes.append("vitals missing")
                    else:
                        vital_value = slot_hr
                        if vital_value is None:
                            self.log.emit(
                                f"WARN — HR missing — {room_bed} ({slot_label})"
                            )
                            self._add_note(
                                run_notes,
                                notes_seen,
                                f"Vitals missing (unexpected) — {room_bed} ({slot_label})",
                            )
                            if "vitals missing" not in record_notes:
                                record_notes.append("vitals missing")

                    decision = decide_for_dose(rule.kind, rule.threshold, vital_value, mark)
                    skip_message = False
                    if decision == "HELD_OK":
                        counts["held_ok"] += 1
                    elif decision == "HOLD_MISS":
                        counts["hold_miss"] += 1
                    elif decision == "COMPLIANT":
                        counts["compliant"] += 1
                    elif decision == "DCD":
                        if not dcd_counted:
                            counts["dcd"] += 1
                            dcd_counted = True
                        else:
                            skip_message = True
                    elif decision == "NONE" and mark == DueMark.CODE_ALLOWED:
                        self.log.emit(
                            f"WARN — allowed code without trigger — {room_bed} ({slot_label})"
                        )
                        self._add_note(
                            run_notes,
                            notes_seen,
                            f"Allowed code without trigger — {room_bed} ({slot_label})",
                        )

                    if not skip_message:
                        message = self._format_decision_log(
                            decision,
                            room_bed,
                            slot_label,
                            rule,
                            slot_bp,
                            slot_hr,
                            mark,
                            mark_text,
                        )
                        self.log.emit(message)

                    if decision == "NONE":
                        continue

                    record_kind = self._decision_label(decision)
                    record_code = self._parse_allowed_code(mark_text) if mark == DueMark.CODE_ALLOWED else None
                    record_vital = self._format_vital_text(rule.kind, slot_bp, slot_hr)
                    record_notes_text = "; ".join(record_notes) if record_notes else None
                    dcd_reason = "X in due cell" if decision == "DCD" else None
                    decision_record = DecisionRecord(
                        hall=hall_name,
                        date_mmddyyyy=audit_date_text,
                        source_basename=source_basename,
                        room_bed=room_bed,
                        dose=slot_name,
                        kind=record_kind,
                        rule_text=rule.description,
                        vital_text=record_vital,
                        code=record_code,
                        dcd_reason=dcd_reason,
                        notes=record_notes_text,
                    )
                    records.append(decision_record)

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
                has_symbol = "<" in line_text or ">" in line_text
                has_words = "less" in lowered or "greater" in lowered
                if not (has_symbol or has_words):
                    continue
                bbox = self._line_bbox(spans)
                if bbox is None:
                    continue
                extended_x1 = min(page.rect.width, band.x1 + 160.0)
                block_bbox = normalize_rect(
                    (
                        max(0.0, min(band.x0 - 120.0, bbox[0] - 12.0)),
                        max(0.0, bbox[1] - 36.0),
                        extended_x1,
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

    def _resolve_room_info(
        self,
        text_dict: dict,
        block_bbox: Tuple[float, float, float, float],
    ) -> Tuple[Optional[Tuple[str, str]], List[Dict[str, object]]]:
        block_rect = normalize_rect(block_bbox)
        gutter_x1 = block_rect[0]
        gutter_x0 = max(0.0, gutter_x1 - 72.0)
        top = block_rect[1]
        bottom = block_rect[3]

        spans = list(
            self._collect_spans(text_dict, gutter_x0, gutter_x1, top, bottom)
        )
        if not spans:
            spans = list(
                self._collect_spans(text_dict, gutter_x0, gutter_x1 + 20.0, top, bottom)
            )
        if not spans:
            spans = list(
                self._collect_spans(text_dict, block_rect[0], block_rect[2], top, bottom)
            )
        if not spans:
            return (None, [])
        return resolve_room_from_block(spans, self._building_master), spans

    @staticmethod
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

    @staticmethod
    def _summarize_room_spans(spans: List[Dict[str, object]]) -> str:
        texts = []
        for span in spans:
            raw = span.get("text")
            if not raw:
                continue
            snippet = re.sub(r"\s+", " ", str(raw)).strip()
            if snippet:
                texts.append(snippet)
            if len(texts) >= 6:
                break
        if not texts:
            return ""
        combined = " ".join(texts)
        if len(combined) > 120:
            combined = combined[:117].rstrip() + "..."
        return f"left gutter text \"{combined}\""

    def _emit_debug_bundle(
        self,
        block_rect: Tuple[float, float, float, float],
        room_bed: str,
        hall_name: str,
        rule_specs: List[RuleSpec],
        row_bands: "RowBands",
        slot_label: str,
        mark: DueMark,
        mark_text: str,
        slot_bp: Optional[str],
        slot_hr: Optional[int],
        split_band_used: bool,
        fallback_used: bool,
    ) -> None:
        rules_desc = ", ".join(f"{spec.kind}@{spec.threshold}" for spec in rule_specs) or "none"
        row_desc = ", ".join(
            [
                f"bp={self._band_summary(row_bands.bp)}",
                f"hr={self._band_summary(row_bands.hr)}",
                f"am={self._band_summary(row_bands.am)}",
                f"pm={self._band_summary(row_bands.pm)}",
            ]
        )
        mark_detail, code_detail = self._mark_details(mark, mark_text)
        mark_summary = self._mark_debug_summary(mark, mark_detail, code_detail)
        vitals_desc = f"BP={slot_bp or '—'} HR={slot_hr if slot_hr is not None else '—'}"
        flags: List[str] = []
        if split_band_used:
            flags.append("split")
        if fallback_used:
            flags.append("fallback")
        if getattr(row_bands, "auto_am_pm_split", False) and "split" not in flags:
            flags.append("split")
        flag_segment = f"; flags={','.join(flags)}" if flags else ""
        self.log.emit(
            "DEBUG — bundle block=(%.1f, %.1f, %.1f, %.1f) room=%s hall=%s slot=%s "
            "rules=[%s] rows=[%s]; mark=%s; %s%s"
            % (
                block_rect[0],
                block_rect[1],
                block_rect[2],
                block_rect[3],
                room_bed,
                hall_name,
                slot_label,
                rules_desc,
                row_desc,
                mark_summary,
                vitals_desc,
                flag_segment,
            )
        )

    @staticmethod
    def _band_summary(band: Optional[Tuple[float, float]]) -> str:
        if band is None:
            return "None"
        top, bottom = band
        return f"({top:.1f}-{bottom:.1f})"

    @staticmethod
    def _mark_debug_summary(
        mark: DueMark,
        mark_detail: Optional[str],
        code_detail: Optional[str],
    ) -> str:
        if mark == DueMark.DCD:
            return "X"
        if mark == DueMark.CODE_ALLOWED:
            return code_detail or "code"
        if mark == DueMark.GIVEN_CHECK:
            return "√"
        if mark == DueMark.GIVEN_TIME:
            return mark_detail or "time"
        return "none"

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
        slot_label: str,
        rule: RuleSpec,
        bp_value: Optional[str],
        hr_value: Optional[int],
        mark: DueMark,
        mark_text: str,
    ) -> str:
        label = self._decision_label(decision)
        mark_detail, code_detail = self._mark_details(mark, mark_text)

        if label == "DC'D":
            desc = mark_detail or "X in due cell"
            return f"{label} — {room_bed} ({slot_label}) — {desc}"

        base = f"{label} — {room_bed} ({slot_label}) — {rule.description}"
        detail_parts: List[str] = []

        if rule.kind.startswith("SBP"):
            detail_parts.append(f"BP {bp_value}" if bp_value else "BP missing")
        else:
            if hr_value is not None:
                detail_parts.append(f"HR {hr_value}")
            else:
                detail_parts.append("HR missing")

        if mark_detail:
            detail_parts.append(mark_detail)

        message = base
        if detail_parts:
            message = f"{base}; {'; '.join(detail_parts)}"
        if code_detail:
            message = f"{message} | {code_detail}"
        return message

    @staticmethod
    def _decision_label(decision: str) -> str:
        if decision == "NONE":
            return "INFO"
        if decision == "DCD":
            return "DC'D"
        return decision.replace("_", "-")

    @staticmethod
    def _mark_details(mark: DueMark, mark_text: str) -> Tuple[Optional[str], Optional[str]]:
        if mark == DueMark.DCD:
            return "X in due cell", None
        if mark == DueMark.CODE_ALLOWED:
            code_match = re.search(r"\b(\d{1,2})\b", mark_text)
            if code_match:
                return None, f"code {code_match.group(1)}"
            return None, "allowed code"
        if mark == DueMark.GIVEN_CHECK:
            return "check mark present", None
        if mark == DueMark.GIVEN_TIME:
            time_match = TIME_RE.search(mark_text)
            if time_match:
                return f"time {time_match.group(0)}", None
            return "time recorded", None
        if mark == DueMark.NONE:
            return None, None
        return None, None

    @staticmethod
    def _empty_summary() -> Dict[str, int]:
        return {
            "reviewed": 0,
            "held_ok": 0,
            "hold_miss": 0,
            "compliant": 0,
            "dcd": 0,
        }

    def _build_output_path(self, audit_date: date, hall: str) -> Path:
        stamp = format_mmddyyyy(audit_date).replace("/", "-")
        hall_upper = hall.upper()
        filename = f"{self._input_pdf.stem}__{stamp}__{hall_upper}.txt"
        return self._input_pdf.with_name(filename)

    @staticmethod
    def _resolve_report_hall(hall_counts: Counter[str]) -> str:
        filtered = Counter(
            {hall: count for hall, count in hall_counts.items() if hall and hall.lower() != "unknown"}
        )
        if not filtered:
            return "UNKNOWN"
        most_common = filtered.most_common()
        top_hall, top_count = most_common[0]
        tied = [hall for hall, count in most_common if count == top_count]
        if len(tied) > 1:
            return "MIXED"
        return top_hall

    @staticmethod
    def _add_note(notes: List[str], seen: set[str], message: str) -> None:
        text = message.strip()
        if not text or text in seen:
            return
        notes.append(text)
        seen.add(text)

    @staticmethod
    def _parse_allowed_code(mark_text: str) -> Optional[int]:
        match = re.search(r"\b(\d{1,2})\b", mark_text)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _format_vital_text(rule_kind: str, bp_value: Optional[str], hr_value: Optional[int]) -> str:
        if rule_kind.startswith("SBP"):
            return f"BP {bp_value}" if bp_value else "BP missing"
        return f"HR {hr_value}" if hr_value is not None else "HR missing"

    @staticmethod
    def _merge_counts(target: Dict[str, int], delta: Dict[str, int]) -> None:
        for key in target:
            target[key] += int(delta.get(key, 0))
