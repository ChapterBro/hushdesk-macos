"""Background worker that simulates auditing a MAR PDF."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import time
from collections import Counter
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from PySide6.QtCore import QObject, Signal, Slot

try:  # pragma: no cover - optional dependency when tests run without PyMuPDF
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from hushdesk.engine.decide import decide_for_dose, rule_triggers
from hushdesk.engine.rules import RuleSpec, parse_rule_text
from hushdesk.fs.exports import exports_dir, sanitize_filename
from hushdesk.id.rooms import load_building_master, resolve_room_from_block
from hushdesk.pdf.columns import ColumnBand, select_audit_columns
from hushdesk.pdf.dates import format_mmddyyyy, resolve_audit_date
from hushdesk.pdf.mar_header import audit_date_from_filename
from hushdesk.pdf.mar_parser_mupdf import run_mar_audit
from hushdesk.pdf.duecell import DueMark, detect_due_mark
from hushdesk.pdf.geometry import normalize_rect
from hushdesk.pdf.rows import find_row_bands_for_block
from hushdesk.pdf.vitals import attach_clusters_to_slots, extract_vitals_in_band
from hushdesk.report.model import DecisionRecord
from hushdesk.report.txt_writer import write_report
from hushdesk.scout.scan import scan_candidates

try:  # pragma: no cover - defensive import guard for optional override helper
    from hushdesk.pdf.dates import dev_override_date as _dev_override_date
except Exception:  # pragma: no cover - keep worker importable when helper missing

    def dev_override_date() -> date | None:
        return None

else:
    dev_override_date = _dev_override_date


logger = logging.getLogger(__name__)

DEBUG_DECISION_DETAILS = False

TIME_RE = re.compile(r"\b(?:[0-1]?\d|2[0-3]):[0-5]\d\b")
CHECKMARK_RE = re.compile(r"[\u221A\u2713\u2714]")
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
    summary_payload = Signal(dict)
    no_data_for_date = Signal()
    finished = Signal(Path)

    def __init__(
        self,
        input_pdf: Path,
        delay: float = 0.2,
        *,
        page_filter: Optional[Iterable[int]] = None,
        trace: bool = False,
        export_dir: Optional[Path] = None,
        hall_override: Optional[str] = None,
        qa_prefix: Optional[Path | str | bool] = None,
    ) -> None:
        super().__init__()
        self._input_pdf = input_pdf
        self._delay = max(0.05, delay)
        self._audit_date: date | None = None
        self._building_master = load_building_master()
        self._unknown_room_debug_warned = False
        self._page_room_cache: Dict[int, Optional[Tuple[str, str]]] = {}
        self._page_filter = {int(index) for index in page_filter} if page_filter else None
        self._trace = bool(trace)
        self._page_render_cache: Dict[int, Tuple[float, int, int]] = {}
        self._export_dir = Path(export_dir).expanduser().resolve() if export_dir else None
        self._hall_override = hall_override.upper() if hall_override else None
        self._qa_prefix = qa_prefix

    @Slot()
    def run(self) -> None:
        self.started.emit(str(self._input_pdf))
        try:
            self._run_canonical()
        except Exception:  # pragma: no cover - defensive guard
            logger.exception("Canonical MAR audit failed")
            self.warning.emit("MAR parser failed; see logs for details")
            self.finished.emit(self._input_pdf)
        return

        # Legacy pipeline retained for reference below this point.

    def _run_canonical(self) -> None:
        override_date = dev_override_date()
        if override_date:
            audit_date = override_date
            audit_date_text = format_mmddyyyy(audit_date)
            label_value = f"{audit_date_text} — Central"
            message = f"DEV: Audit Date overridden to {label_value}"
            logger.info(message)
            self.log.emit(message)
        else:
            try:
                audit_dt, audit_date_text = audit_date_from_filename(self._input_pdf)
                audit_date = audit_dt.date()
            except ValueError:
                audit_date = resolve_audit_date(self._input_pdf)
                audit_date_text = format_mmddyyyy(audit_date)
            label_value = f"{audit_date_text} — Central"

        self._audit_date = audit_date
        self.audit_date_text.emit(label_value)
        if not self._input_pdf.exists():
            self.warning.emit("Input MAR PDF not found; emitting no-data signal.")
            self.no_data_for_date.emit()
            return

        hall_value = self._hall_override or "UNKNOWN"
        result = run_mar_audit(
            self._input_pdf,
            hall_value,
            audit_date,
            qa_prefix=self._qa_prefix,
        )

        if result.instrument_line:
            self.log.emit(result.instrument_line)

        if not result.records:
            self.no_data_for_date.emit()

        counts = dict(result.counts)
        self.summary_counts.emit(counts)

        payload_records = [
            self._record_payload(index, record)
            for index, record in enumerate(result.records)
        ]
        payload = {
            "counts": counts,
            "records": payload_records,
            "anomalies": [],
            "source_pdf": str(self._input_pdf),
            "hall": result.hall,
            "audit_date_text": result.audit_date_mmddyyyy,
            "qa_paths": [str(path) for path in result.qa_paths],
            "summary_line": result.summary_line,
            "blocks": result.blocks,
            "tracks": result.tracks,
            "instrumentation": dict(result.instrumentation),
            "instrument_line": result.instrument_line,
        }
        self.summary_payload.emit(payload)

        total_blocks = max(result.blocks, 1)
        for index in range(1, total_blocks + 1):
            self.progress.emit(index, total_blocks)

        export_dir = self._export_dir or exports_dir()
        export_dir.mkdir(parents=True, exist_ok=True)
        base_name = Path(result.source_basename).stem
        report_name = sanitize_filename(
            f"{result.audit_date_mmddyyyy}_{result.hall}_{base_name}.txt"
        )
        report_path = export_dir / report_name
        report_path = write_report(
            records=result.records,
            counts=result.counts,
            audit_date_mmddyyyy=result.audit_date_mmddyyyy,
            hall=result.hall,
            source_basename=result.source_basename,
            out_path=report_path,
        )

        self.log.emit(result.summary_line)
        if result.qa_paths:
            self.log.emit(
                f"QA overlays saved ({len(result.qa_paths)}) to {result.qa_paths[0].parent}"
            )
        self.log.emit(f"Report saved: {report_path}")
        self.saved.emit(str(report_path))
        self.finished.emit(report_path)
        return

        scout_enabled = os.getenv("HUSHDESK_SCOUT") == "1"

        column_bands: List[ColumnBand] = []
        missing_headers: List[int] = []
        counters = self._empty_summary()
        records: List[DecisionRecord] = []
        record_payloads: List[dict] = []
        anomalies: List[dict] = []
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
                    if self._page_filter is not None:
                        column_bands = [
                            band for band in column_bands if band.page_index in self._page_filter
                        ]
                    self.log.emit(
                        f"Processing {len(column_bands)} band pages (of {doc_pages} total pages)"
                    )
                    if scout_enabled and column_bands:
                        self._emit_scout_candidates(doc, audit_date, column_bands)
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
                            band_trace: Optional[List[Dict[str, object]]] = [] if self._trace else None
                            if self._trace:
                                self._emit_band_spans(page, band)
                            band_counts = self._evaluate_column_band(
                                page,
                                band,
                                audit_date_text,
                                self._input_pdf.name,
                                records,
                                record_payloads,
                                anomalies,
                                hall_counts,
                                run_notes,
                                notes_seen,
                                trace_log=band_trace,
                            )
                            if self._trace and band_trace:
                                self._emit_fallback_trace(band.page_index, band_trace)
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

        detected_hall = self._resolve_report_hall(hall_counts)
        hall = self._hall_override or detected_hall
        if self._hall_override and detected_hall and detected_hall != self._hall_override:
            message = f"Hall override applied: requested {self._hall_override} (detected {detected_hall})"
            logger.info(message)
            self.log.emit(message)
        if hall == "UNKNOWN":
            self._add_note(run_notes, notes_seen, "Hall could not be resolved from room-bed tokens")
        elif hall == "MIXED":
            self._add_note(run_notes, notes_seen, "Rooms span multiple halls (mixed)")

        summary_counts_copy = dict(counters)
        payload_snapshot = {
            "counts": summary_counts_copy,
            "records": [deepcopy(payload) for payload in record_payloads],
            "notes": list(run_notes),
            "anomalies": [deepcopy(entry) for entry in anomalies],
            "source_pdf": str(self._input_pdf),
            "hall": hall,
            "audit_date_text": audit_date_text,
        }
        self.summary_counts.emit(summary_counts_copy)
        self.summary_payload.emit(payload_snapshot)

        output_path = self._build_output_path(audit_date, hall)
        try:
            final_path = write_report(
                records,
                counters,
                audit_date_text,
                hall,
                self._input_pdf.name,
                output_path,
                run_notes,
            )
            if final_path != output_path:
                self.log.emit(
                    f"Permission denied writing to {output_path}; fallback to {final_path}"
                )
            output_path = final_path
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
        record_payloads: List[dict],
        anomalies: List[dict],
        hall_counts: Counter[str],
        run_notes: List[str],
        notes_seen: set[str],
        trace_log: Optional[List[Dict[str, object]]] = None,
    ) -> Dict[str, int]:
        counts = self._empty_summary()
        try:
            text_dict = page.get_text("dict")
        except RuntimeError:
            return counts
        scale, page_width_px, page_height_px = self._page_render_metrics(page)

        block_candidates = self._find_block_candidates(page, band, text_dict)
        for block_bbox, rule_text in block_candidates:
            rule_specs = parse_rule_text(rule_text)
            if not rule_specs:
                continue

            row_bands = find_row_bands_for_block(page, block_bbox)
            block_rect = normalize_rect(block_bbox)
            room_info, room_spans = self._resolve_room_info(band.page_index, text_dict, block_rect)
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

            for candidate_name, candidate_band in slot_bands.items():
                if candidate_band is None:
                    self._append_anomaly(
                        anomalies,
                        "zero_width_band",
                        room_bed,
                        candidate_name,
                        band.page_index,
                        f"Zero-width band dropped — {room_bed} ({candidate_name})",
                        None,
                    )

            slot_sequence = [(name, band) for name, band in slot_bands.items() if band is not None]
            if not slot_sequence:
                continue

            dose_bounds_map = {name: band for name, band in slot_bands.items() if band is not None}

            bp_band = self._expand_band(row_bands.bp, block_rect)
            hr_band = self._expand_band(row_bands.hr, block_rect)

            bp_result: Optional[Dict[str, object]] = None
            hr_result: Optional[Dict[str, object]] = None
            bp_value = None
            hr_value = None
            slot_x0 = max(band.x0, block_rect[0])
            slot_x1 = block_rect[2]
            if bp_band is not None:
                bp_result = extract_vitals_in_band(
                    page,
                    slot_x0,
                    slot_x1,
                    *bp_band,
                    dose_bands=dose_bounds_map,
                )
                self._extend_fallback_trace(trace_log, bp_result, context="BP")
                bp_value = bp_result.get("bp")
            if hr_band is not None:
                hr_result = extract_vitals_in_band(
                    page,
                    slot_x0,
                    slot_x1,
                    *hr_band,
                    allow_plain_hr=True,
                    dose_bands=dose_bounds_map,
                )
                self._extend_fallback_trace(trace_log, hr_result, context="HR")
                hr_value = hr_result.get("hr")

            slot_rect_map_points: Dict[str, Optional[Tuple[float, float, float, float]]] = {}
            for slot_label_name, slot_bounds in dose_bounds_map.items():
                slot_rect_map_points[slot_label_name] = self._build_slot_rect(
                    slot_x0,
                    slot_x1,
                    slot_bounds,
                )

            if split_band_used:
                self.log.emit(
                    f"WARN — AM/PM labels missing, using 50/50 split for block {room_bed}"
                )
            elif fallback_used:
                self.log.emit(
                    f"WARN — fallback slot band used — {room_bed}"
                )

            fallback_rows_pool: List[Dict[str, object]] = []
            fallback_row_keys: set[Tuple[float, str, Optional[int]]] = set()

            def _collect_fallback_rows(rows: object) -> None:
                if not isinstance(rows, list):
                    return
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    y_mid = float(row.get("y_mid", 0.0))
                    bp_text = row.get("bp")
                    hr_value = row.get("hr") if isinstance(row.get("hr"), int) else None
                    key = (round(y_mid, 1), str(bp_text), hr_value)
                    if key in fallback_row_keys:
                        continue
                    fallback_row_keys.add(key)
                    fallback_rows_pool.append(dict(row))

            if bp_result:
                _collect_fallback_rows(bp_result.get("_fallback_rows"))
            if hr_result:
                _collect_fallback_rows(hr_result.get("_fallback_rows"))

            slot_states: List[Dict[str, object]] = []
            for slot_name, slot_band in slot_sequence:
                slot_label = slot_name
                if split_band_used:
                    slot_label = f"{slot_name} (split)"
                elif fallback_used:
                    slot_label = f"{slot_name} (fallback)"

                slot_vitals = extract_vitals_in_band(
                    page,
                    slot_x0,
                    slot_x1,
                    *slot_band,
                    dose_hint=slot_name,
                    dose_bands=dose_bounds_map,
                )
                self._extend_fallback_trace(
                    trace_log,
                    slot_vitals,
                    context=f"SLOT:{slot_name}",
                    dose_label=slot_name,
                )
                _collect_fallback_rows(slot_vitals.get("_fallback_rows"))

                slot_bp_raw = slot_vitals.get("bp")
                slot_hr_raw = slot_vitals.get("hr")
                slot_bp = slot_bp_raw or bp_value
                slot_hr = slot_hr_raw or hr_value
                sbp_value = self._sbp_from_bp(slot_bp)

                if slot_band:
                    slot_top, slot_bottom = sorted(slot_band)
                    slot_mid = (slot_top + slot_bottom) / 2.0
                    slot_half_height = abs(slot_bottom - slot_top) / 2.0
                else:
                    slot_mid = 0.0
                    slot_half_height = 0.0
                slot_tolerance = max(slot_half_height, 12.0) + 8.0

                mark = detect_due_mark(page, slot_x0, slot_x1, *slot_band)
                mark_text = self._collect_text(page, slot_x0, slot_x1, *slot_band)
                code_value = self._parse_allowed_code(mark_text) if mark == DueMark.CODE_ALLOWED else None

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

                slot_states.append(
                    {
                        "name": slot_name,
                        "label": slot_label,
                        "band": slot_band,
                        "slot_x0": slot_x0,
                        "slot_x1": slot_x1,
                        "bp": slot_bp,
                        "hr": slot_hr,
                        "sbp": sbp_value,
                        "mark": mark,
                        "mark_text": mark_text,
                        "code": code_value,
                        "record_notes": record_notes,
                        "bp_label_missing": slot_bp_raw is None,
                        "hr_label_missing": slot_hr_raw is None,
                        "cluster": None,
                        "slot_mid": slot_mid,
                        "tolerance": slot_tolerance,
                        "split_used": split_band_used,
                        "fallback_used": fallback_used,
                        "vitals": slot_vitals,
                    }
                )

            need_cluster_attachment = any(
                state.get("bp_label_missing")
                or state.get("hr_label_missing")
                or state["bp"] is None
                or state["hr"] is None
                for state in slot_states
            )
            slot_cluster_result: Dict[str, object] = {}
            if need_cluster_attachment and fallback_rows_pool and dose_bounds_map:
                slot_cluster_result = attach_clusters_to_slots(fallback_rows_pool, dose_bounds_map)

            for state in slot_states:
                cluster_info: Optional[Dict[str, object]] = None
                cluster_assigned = False
                if slot_cluster_result:
                    candidate = slot_cluster_result.get(state["name"].upper())
                    if isinstance(candidate, dict):
                        cluster_info = dict(candidate)
                        assigned_flag = cluster_info.get("assigned")
                        if isinstance(assigned_flag, bool):
                            cluster_assigned = assigned_flag
                        else:
                            cluster_assigned = bool(cluster_info.get("bp")) or isinstance(cluster_info.get("hr"), int)
                state["cluster"] = cluster_info
                state["cluster_assigned"] = cluster_assigned
                state["cluster_y"] = cluster_info.get("y") if isinstance(cluster_info, dict) else None
                if cluster_assigned and cluster_info:
                    if (state["bp"] is None or state.get("bp_label_missing")) and isinstance(cluster_info.get("bp"), str):
                        state["bp"] = cluster_info["bp"]
                        state["sbp"] = self._sbp_from_bp(state["bp"])
                        state["bp_label_missing"] = False
                    if (state["hr"] is None or state.get("hr_label_missing")) and isinstance(cluster_info.get("hr"), int):
                        state["hr"] = cluster_info["hr"]
                        state["hr_label_missing"] = False

            for state in slot_states:
                slot_name = state["name"]
                slot_label = state["label"]
                slot_band = state["band"]
                slot_bp = state["bp"]
                slot_hr = state["hr"]
                sbp_value = state["sbp"]
                mark = state["mark"]
                mark_text = state["mark_text"]
                code_value = state["code"]
                record_notes = state["record_notes"]
                cluster_info = state["cluster"]
                cluster_assigned = bool(state.get("cluster_assigned"))
                given_detected = mark in (DueMark.GIVEN_CHECK, DueMark.GIVEN_TIME)

                tolerance = float(state.get("tolerance", 0.0))
                slot_mid = float(state.get("slot_mid", 0.0))
                cluster_y_value = state.get("cluster_y")
                cluster_y = None
                if cluster_y_value is not None:
                    try:
                        cluster_y = float(cluster_y_value)  # type: ignore[arg-type]
                    except (TypeError, ValueError):
                        cluster_y = None

                if tolerance > 0.0:
                    detection = self._detect_given_with_tolerance(page, slot_x0, slot_x1, slot_mid, tolerance)
                    if detection in (DueMark.GIVEN_CHECK, DueMark.GIVEN_TIME):
                        given_detected = True
                        if mark == DueMark.NONE:
                            mark = detection
                    if cluster_y is not None:
                        detection = self._detect_given_with_tolerance(page, slot_x0, slot_x1, cluster_y, tolerance)
                        if detection in (DueMark.GIVEN_CHECK, DueMark.GIVEN_TIME):
                            given_detected = True
                            if mark == DueMark.NONE:
                                mark = detection

                state["mark"] = mark
                state["given_detected"] = given_detected
                explicit_mark = mark in (DueMark.GIVEN_CHECK, DueMark.GIVEN_TIME, DueMark.CODE_ALLOWED)

                if slot_band is not None:
                    y_summary = f"[{slot_band[0]:.1f},{slot_band[1]:.1f}]"
                else:
                    y_summary = "[-, -]"
                cluster_y_text = f"{float(cluster_y):.1f}" if cluster_y is not None else "-"
                assigned_text = "True" if cluster_assigned else "False"
                bp_text = str(slot_bp) if slot_bp else "-"
                hr_text = str(slot_hr) if slot_hr is not None else "-"
                code_text = str(code_value) if code_value is not None else "-"
                given_text = "True" if given_detected else "False"

                vitals_missing_noted = False
                dcd_counted = False

                for rule in rule_specs:
                    if rule.kind.startswith("SBP"):
                        vital_value = sbp_value
                        missing_label = "SBP"
                        vital_for_trace = slot_bp or "-"
                    else:
                        vital_value = slot_hr
                        missing_label = "HR"
                        vital_for_trace = str(slot_hr) if slot_hr is not None else "-"

                    if vital_value is None and explicit_mark and not cluster_assigned:
                        self.log.emit(
                            f"WARN — {missing_label} missing — {room_bed} ({slot_label})"
                        )
                        if not vitals_missing_noted:
                            self._add_note(
                                run_notes,
                                notes_seen,
                                f"Vitals missing (unexpected) — {room_bed} ({slot_label})",
                            )
                            if "vitals missing" not in record_notes:
                                record_notes.append("vitals missing")
                            vitals_missing_noted = True

                    triggered = rule_triggers(rule.kind, rule.threshold, vital_value)
                    decision = decide_for_dose(rule.kind, rule.threshold, vital_value, mark)
                    skip_message = False
                    if decision == "HELD_OK":
                        counts["held_appropriate"] += 1
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
                        self._append_anomaly(
                            anomalies,
                            "allowed_code_without_trigger",
                            room_bed,
                            slot_label,
                            band.page_index,
                            f"Allowed code without trigger — {room_bed} ({slot_label})",
                            None,
                            {"code": code_value},
                        )

                    decision_display = "DC'D" if decision == "DCD" else decision.replace("_", "-")
                    trigger_text = "True" if triggered else "False"
                    rule_slug = f"{rule.kind}{rule.threshold}"
                    trace_message = (
                        f"TRACE — slot {slot_name} rule={rule_slug} y={y_summary} cluster_y={cluster_y_text} "
                        f"assigned={assigned_text} bp={bp_text} hr={hr_text} vital={vital_for_trace} "
                        f"given={given_text} code={code_text} triggered={trigger_text} "
                        f"→ decision={decision_display}"
                    )
                    self.log.emit(trace_message)

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
                    record_vital = self._format_vital_text(rule.kind, slot_bp, slot_hr)
                    record_notes_text = "; ".join(record_notes) if record_notes else None
                    dcd_reason = "X in due cell" if decision == "DCD" else None
                    mark_display = self._format_mark_display(mark, mark_text, code_value)
                    dy_value = None
                    if cluster_y is not None:
                        try:
                            dy_value = float(cluster_y) - float(slot_mid)
                        except (TypeError, ValueError):
                            dy_value = None
                    slot_rect = self._build_slot_rect(state.get("slot_x0"), state.get("slot_x1"), slot_band)
                    due_rect = slot_rect
                    source_flags = self._build_source_flags(
                        state,
                        fallback_used,
                        split_band_used,
                        cluster_assigned,
                        given_detected,
                        explicit_mark,
                    )
                    source_type = self._resolve_source_type(source_flags)
                    token_boxes = self._build_token_boxes(state.get("vitals"), due_rect)
                    overlay_pixels = self._build_overlay_payload(
                        band_rect=self._band_rect_tuple(band),
                        slot_rects=slot_rect_map_points,
                        token_boxes=token_boxes,
                        scale=scale,
                        page_width_px=page_width_px,
                        page_height_px=page_height_px,
                        active_slot=slot_name,
                        slot_bp=slot_bp,
                        slot_hr=slot_hr,
                    )
                    dy_px = float(dy_value) * scale if isinstance(dy_value, (int, float)) else None
                    cluster_y_px = float(cluster_y) * scale if isinstance(cluster_y, (int, float)) else None
                    source_meta: Dict[str, object] = {"vital_source": source_type}
                    if dy_px is not None:
                        source_meta["dy_px"] = dy_px
                    if cluster_y_px is not None:
                        source_meta["cluster_y_px"] = cluster_y_px
                    extras: Dict[str, object] = {
                        "mark_display": mark_display,
                        "mark_type": mark.name,
                        "mark_text": mark_text.strip() if mark_text else "",
                        "rule_kind": rule.kind,
                        "rule_threshold": rule.threshold,
                        "triggered": triggered,
                        "decision_raw": decision,
                        "exception": record_kind in {"HOLD-MISS", "HELD-APPROPRIATE"},
                        "page_index": band.page_index,
                        "page_number": band.page_index + 1,
                        "page_width": float(band.page_width),
                        "page_height": float(band.page_height),
                        "band_rect": self._band_rect_tuple(band),
                        "slot_band": self._slot_band_tuple(slot_band),
                        "slot_rect": slot_rect,
                        "due_rect": due_rect,
                        "token_boxes": token_boxes,
                        "overlay_pixels": overlay_pixels,
                        "source_meta": source_meta,
                        "source_flags": source_flags,
                        "source_type": source_type,
                        "slot_label": slot_label,
                        "slot_name": slot_name,
                        "cluster_y": cluster_y,
                        "slot_mid": slot_mid,
                        "dy": dy_value,
                        "tolerance": tolerance,
                        "given_detected": given_detected,
                        "explicit_mark": explicit_mark,
                        "notes_list": list(record_notes),
                    }
                    decision_record = DecisionRecord(
                        hall=hall_name,
                        date_mmddyyyy=audit_date_text,
                        source_basename=source_basename,
                        room_bed=room_bed,
                        dose=slot_name,
                        kind=record_kind,
                        rule_text=rule.description,
                        vital_text=record_vital,
                        code=code_value,
                        dcd_reason=dcd_reason,
                        notes=record_notes_text,
                        extras=extras,
                    )
                    records.append(decision_record)
                    payload_entry = self._record_payload(len(record_payloads), decision_record)
                    record_payloads.append(payload_entry)
                    record_id = payload_entry.get("id")
                    if mark == DueMark.NONE:
                        self._append_anomaly(
                            anomalies,
                            "missing_due_mark",
                            room_bed,
                            slot_label,
                            band.page_index,
                            f"Missing due mark — {room_bed} ({slot_label})",
                            int(record_id) if isinstance(record_id, int) else None,
                            {
                                "mark": mark_display,
                                "source": extras.get("source_type"),
                            },
                        )
                    if rule.kind.startswith("SBP") and not slot_bp:
                        self._append_anomaly(
                            anomalies,
                            "no_bp_value",
                            room_bed,
                            slot_label,
                            band.page_index,
                            f"No BP captured in slot — {room_bed} ({slot_label})",
                            int(record_id) if isinstance(record_id, int) else None,
                            {
                                "source": extras.get("source_type"),
                            },
                        )

        return counts

    def _find_block_candidates(
        self,
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
                if not line_text:
                    continue
                lowered = line_text.lower()
                if "hold" not in lowered:
                    continue
                bbox = self._line_bbox(spans)
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
                    self._collect_spans(
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
        page_index: int,
        text_dict: dict,
        block_bbox: Tuple[float, float, float, float],
    ) -> Tuple[Optional[Tuple[str, str]], List[Dict[str, object]]]:
        cached = self._page_room_cache.get(page_index)
        if cached is None:
            cached = self._resolve_room_for_page(page_index, text_dict)
            self._page_room_cache[page_index] = cached
        if cached:
            return cached, []
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

    def _resolve_room_for_page(
        self,
        page_index: int,
        text_dict: dict,
    ) -> Optional[Tuple[str, str]]:
        header_limit = 220.0
        spans: List[Dict[str, object]] = []
        for block in text_dict.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text")
                    bbox = span.get("bbox")
                    if not text or not bbox:
                        continue
                    sx0, sy0, sx1, sy1 = normalize_rect(tuple(map(float, bbox)))
                    if sy1 <= header_limit:
                        spans.append({"text": text})
        if spans:
            page_room = resolve_room_from_block(spans, self._building_master)
            if page_room:
                return page_room
        return None

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
    def _collect_spans_in_band(
        page: "fitz.Page",
        x0: float,
        x1: float,
        y0: float,
        y1: float,
    ) -> List[Tuple[str, Tuple[float, float, float, float]]]:
        rect = normalize_rect((x0, y0, x1, y1))
        try:
            text_dict = page.get_text("dict")
        except RuntimeError:
            return []

        spans: List[Tuple[str, Tuple[float, float, float, float]]] = []
        for block in text_dict.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    raw_text = span.get("text")
                    bbox = span.get("bbox")
                    if not raw_text or not bbox:
                        continue
                    sx0, sy0, sx1, sy1 = map(float, bbox)
                    center_x = (sx0 + sx1) / 2.0
                    if center_x < rect[0] or center_x > rect[2]:
                        continue
                    if sy1 < rect[1] or sy0 > rect[3]:
                        continue
                    spans.append((str(raw_text), (sx0, sy0, sx1, sy1)))
        return spans

    @staticmethod
    def _detect_given_with_tolerance(
        page: "fitz.Page",
        x0: float,
        x1: float,
        center_y: Optional[float],
        tolerance: float,
    ) -> Optional[DueMark]:
        if center_y is None or tolerance <= 0.0:
            return None
        top = center_y - tolerance
        bottom = center_y + tolerance
        if top > bottom:
            top, bottom = bottom, top
        spans = AuditWorker._collect_spans_in_band(page, x0, x1, top, bottom)
        if not spans:
            return None
        for text, _ in spans:
            if CHECKMARK_RE.search(text):
                return DueMark.GIVEN_CHECK
        for text, _ in spans:
            if TIME_RE.search(text):
                return DueMark.GIVEN_TIME
        return None

    @staticmethod
    def _extend_fallback_trace(
        trace_log: Optional[List[Dict[str, object]]],
        result: Optional[Dict[str, object]],
        *,
        context: str,
        dose_label: Optional[str] = None,
    ) -> None:
        if trace_log is None or not result or not dose_label:
            return
        rows = result.get("_fallback_rows")
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                y_mid = float(row.get("y_mid", 0.0))
                if any(
                    existing.get("dose") == dose_label
                    and abs(float(existing.get("y_mid", 0.0)) - y_mid) < 0.1
                    for existing in trace_log
                ):
                    continue
                entry = dict(row)
                entry["dose"] = dose_label
                entry["context"] = context
                trace_log.append(entry)
        selected = result.get("_fallback_selected")
        if isinstance(selected, dict):
            entry = dict(selected)
            y_mid = float(entry.get("y_mid", 0.0))
            for existing in trace_log:
                if (
                    existing.get("dose") == dose_label
                    and abs(float(existing.get("y_mid", 0.0)) - y_mid) < 0.1
                ):
                    existing["selected"] = True
                    break
            else:
                entry["dose"] = dose_label
                entry["context"] = context
                entry["selected"] = True
                trace_log.append(entry)

    def _emit_band_spans(self, page: "fitz.Page", band: ColumnBand) -> None:
        if fitz is None or not hasattr(page, "rect"):
            return
        try:
            page_rect = page.rect
        except Exception:  # pragma: no cover - defensive
            return
        clip_left = max(0.0, min(band.x0, band.x1))
        clip_right = min(float(page_rect.x1), max(band.x0, band.x1))
        if clip_right <= clip_left:
            return
        try:
            clip_rect = fitz.Rect(clip_left, 0.0, clip_right, float(page_rect.y1))
            text_dict = page.get_text("dict", clip=clip_rect)
        except RuntimeError:
            self.log.emit(f"TRACE — page {band.page_index + 1}: unable to collect spans for trace")
            return

        span_rows: List[Tuple[float, str]] = []
        for block in text_dict.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    raw_text = span.get("text")
                    bbox = span.get("bbox")
                    if not raw_text or not bbox:
                        continue
                    _, sy0, _, sy1 = map(float, bbox)
                    y_mid = (sy0 + sy1) / 2.0
                    snippet = re.sub(r"\s+", " ", str(raw_text)).strip()
                    span_rows.append((y_mid, snippet))
        span_rows.sort(key=lambda item: item[0])
        summary = f"TRACE — page {band.page_index + 1} spans={len(span_rows)} x=({band.x0:.1f},{band.x1:.1f})"
        self.log.emit(summary)
        for y_mid, text in span_rows:
            if not text:
                continue
            preview = text if len(text) <= 160 else text[:157].rstrip() + "..."
            self.log.emit(f"TRACE —   y={y_mid:.1f} text=\"{preview}\"")

    def _emit_fallback_trace(self, page_index: int, trace_rows: List[Dict[str, object]]) -> None:
        if not trace_rows:
            return
        unique_rows: List[Dict[str, object]] = []
        seen: set[Tuple[float, str, str]] = set()
        for row in trace_rows:
            y_mid = float(row.get("y_mid", 0.0))
            text = str(row.get("text", "")).strip()
            dose = str(row.get("dose", row.get("context", "")) or "")
            key = (round(y_mid, 1), text, dose)
            if key in seen:
                continue
            seen.add(key)
            row_copy = dict(row)
            row_copy.setdefault("dose", dose or "-")
            row_copy.setdefault("text", text)
            if "context" not in row_copy:
                row_copy["context"] = ""
            unique_rows.append(row_copy)
        if not unique_rows:
            return
        self.log.emit(f"TRACE — fallback clusters page {page_index + 1}:")
        for row in unique_rows:
            y_mid = float(row.get("y_mid", 0.0))
            bp_value = row.get("bp") or "—"
            if not isinstance(bp_value, str):
                bp_value = str(bp_value)
            hr_value = row.get("hr")
            hr_text = hr_value if isinstance(hr_value, int) else "—"
            dose = row.get("dose") or "-"
            preview = str(row.get("text", "")).strip()
            if len(preview) > 160:
                preview = preview[:157].rstrip() + "..."
            star = "*" if row.get("selected") else " "
            self.log.emit(
                f"TRACE —   {star} y={y_mid:.1f} dose={dose} bp={bp_value} hr={hr_text} text=\"{preview}\""
            )

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
        if code_detail:
            detail_parts.append(code_detail)

        if detail_parts:
            return f"{base}; {'; '.join(detail_parts)}"
        return base

    @staticmethod
    def _decision_label(decision: str) -> str:
        if decision == "NONE":
            return "INFO"
        if decision == "DCD":
            return "DC'D"
        if decision == "HELD_OK":
            return "HELD-APPROPRIATE"
        return decision.replace("_", "-")

    @staticmethod
    def _mark_details(mark: DueMark, mark_text: str) -> Tuple[Optional[str], Optional[str]]:
        if mark == DueMark.DCD:
            return "X in due cell", None
        if mark == DueMark.CODE_ALLOWED:
            code_value = AuditWorker._parse_allowed_code(mark_text)
            if code_value is not None:
                return None, f"code {code_value}"
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

    def _emit_scout_candidates(
        self,
        doc: "fitz.Document",
        audit_date: date,
        bands: Sequence[ColumnBand],
    ) -> None:
        try:
            candidates = scan_candidates(doc, audit_date, bands)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Scout scan failed for %s: %s", self._input_pdf, exc, exc_info=True)
            self.log.emit(f"SCOUT — error during scan: {exc}")
            return

        if not candidates:
            self.log.emit("SCOUT — no rule candidates detected")
            return

        ranked = sorted(
            candidates,
            key=lambda item: (
                1 if (item.has_code or item.has_time) else 0,
                1 if item.has_code else 0,
                len(item.rule_kinds),
                -item.page,
            ),
            reverse=True,
        )

        for candidate in ranked[:10]:
            rules_segment = ", ".join(candidate.rule_kinds)
            room = candidate.room_bed or "Unknown"
            dose = candidate.dose or "-"
            message = (
                f"SCOUT — p={candidate.page} room={room} dose={dose} "
                f"code={candidate.has_code} time={candidate.has_time} "
                f"rules=[{rules_segment}]"
            )
            self.log.emit(message)

    @staticmethod
    def _empty_summary() -> Dict[str, int]:
        return {
            "reviewed": 0,
            "held_appropriate": 0,
            "hold_miss": 0,
            "compliant": 0,
            "dcd": 0,
        }

    def _build_output_path(self, audit_date: date, hall: str) -> Path:
        stamp = format_mmddyyyy(audit_date).replace("/", "-")
        hall_upper = (hall or "UNKNOWN").upper()
        filename = f"{self._input_pdf.stem}__{stamp}__{hall_upper}.txt"
        sanitized = sanitize_filename(filename)
        export_root = self._export_dir or exports_dir()
        export_root.mkdir(parents=True, exist_ok=True)
        return export_root / sanitized

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
        vitals_key = AuditWorker._vitals_note_key(text)
        if vitals_key:
            sentinel = f"__vitals__{vitals_key[0]}__{vitals_key[1]}"
            if sentinel in seen:
                return
            seen.add(sentinel)
        notes.append(text)
        seen.add(text)

    @staticmethod
    def _vitals_note_key(message: str) -> Optional[Tuple[str, str]]:
        match = re.match(
            r"(?i)^vitals\s+missing\s*\(unexpected\)\s*—\s*(?P<room>[^()]+?)\s*\((?P<dose>[^)]+)\)",
            message,
        )
        if not match:
            return None
        room = match.group("room").strip()
        dose_token = match.group("dose").strip()
        if not room or not dose_token:
            return None
        base_dose = dose_token.split()[0].strip().upper()
        if not base_dose:
            return None
        return room, base_dose

    @staticmethod
    def _parse_allowed_code(mark_text: str) -> Optional[int]:
        allowed = {"4", "6", "11", "12", "15"}
        for match in re.findall(r"\b(\d{1,2})\b", mark_text):
            if match in allowed:
                try:
                    return int(match)
                except ValueError:
                    continue
        return None

    @staticmethod
    def _format_vital_text(rule_kind: str, bp_value: Optional[str], hr_value: Optional[int]) -> str:
        if rule_kind.startswith("SBP"):
            return f"BP {bp_value}" if bp_value else "BP missing"
        return f"HR {hr_value}" if hr_value is not None else "HR missing"

    @staticmethod
    def _format_mark_display(mark: DueMark, mark_text: str, code_value: Optional[int]) -> str:
        if mark == DueMark.DCD:
            return "X"
        if mark == DueMark.CODE_ALLOWED:
            if code_value is not None:
                return f"code {code_value}"
            parsed = AuditWorker._parse_allowed_code(mark_text)
            if parsed is not None:
                return f"code {parsed}"
            return "code"
        if mark == DueMark.GIVEN_CHECK:
            return "√"
        if mark == DueMark.GIVEN_TIME:
            match = TIME_RE.search(mark_text)
            if match:
                return match.group(0)
            text = mark_text.strip()
            return text or "time"
        return "—"

    @staticmethod
    def _record_payload(record_id: int, record: DecisionRecord) -> Dict[str, object]:
        extras_copy = dict(record.extras) if record.extras else {}
        mark_display = str(extras_copy.get("mark_display") or "")
        exception_flag = bool(extras_copy.get("exception"))
        slot_label = extras_copy.get("slot_label") or record.dose
        source_type = extras_copy.get("source_type") or "label"
        page_index = extras_copy.get("page_index")
        overlay_pixels = extras_copy.get("overlay_pixels")
        if not isinstance(overlay_pixels, dict):
            overlay_pixels = {}
        preview_meta = getattr(record, "preview", None)
        preview_payload = dict(preview_meta) if isinstance(preview_meta, dict) else None
        source_meta = extras_copy.get("source_meta")
        if not isinstance(source_meta, dict):
            source_meta = {}
        audit_band = overlay_pixels.get("audit_band")
        slot_bboxes = overlay_pixels.get("slot_bboxes") if isinstance(overlay_pixels.get("slot_bboxes"), dict) else {}
        vital_bbox = overlay_pixels.get("vital_bbox")
        mark_bboxes = overlay_pixels.get("mark_bboxes") if isinstance(overlay_pixels.get("mark_bboxes"), list) else []
        overlay_labels = overlay_pixels.get("labels") if isinstance(overlay_pixels.get("labels"), list) else []
        page_pixels = overlay_pixels.get("page") if isinstance(overlay_pixels.get("page"), dict) else {}
        search_parts = [
            record.room_bed,
            slot_label,
            record.kind,
            record.rule_text,
            record.vital_text,
            str(record.code) if record.code is not None else "",
            mark_display,
            record.notes or "",
            source_type,
        ]
        search_blob = " ".join(part for part in search_parts if part).lower()
        payload = {
            "id": record_id,
            "kind": record.kind,
            "room_bed": record.room_bed,
            "dose": record.dose,
            "slot_label": slot_label,
            "rule_text": record.rule_text,
            "vital_text": record.vital_text,
            "code": record.code,
            "dcd_reason": record.dcd_reason,
            "notes": record.notes,
            "mark_display": mark_display,
            "exception": exception_flag,
            "source_type": source_type,
            "triggered": bool(extras_copy.get("triggered")),
            "page_index": int(page_index) if isinstance(page_index, int) else None,
            "extras": extras_copy,
            "page_pixels": dict(page_pixels),
            "audit_band": tuple(audit_band) if isinstance(audit_band, (list, tuple)) else audit_band,
            "slot_bboxes": {str(key): tuple(value) for key, value in slot_bboxes.items()} if isinstance(slot_bboxes, dict) else {},
            "vital_bbox": tuple(vital_bbox) if isinstance(vital_bbox, (list, tuple)) else None,
            "mark_bboxes": [tuple(rect) for rect in mark_bboxes if isinstance(rect, (list, tuple))],
            "vital_boxes": [tuple(rect) for rect in overlay_pixels.get("vital_boxes", []) if isinstance(rect, (list, tuple))],
            "overlay_labels": list(overlay_labels),
            "source_meta": dict(source_meta),
            "search_blob": search_blob,
        }
        if preview_payload:
            payload["preview"] = preview_payload
        return payload

    @staticmethod
    def _band_rect_tuple(band: ColumnBand) -> Tuple[float, float, float, float]:
        return (float(band.x0), 0.0, float(band.x1), float(band.page_height))

    @staticmethod
    def _slot_band_tuple(bounds: Optional[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
        if bounds is None:
            return None
        top, bottom = bounds
        if bottom < top:
            top, bottom = bottom, top
        return (float(top), float(bottom))

    @staticmethod
    def _build_slot_rect(slot_x0: Optional[float], slot_x1: Optional[float], slot_band: Optional[Tuple[float, float]]) -> Optional[Tuple[float, float, float, float]]:
        if slot_x0 is None or slot_x1 is None or slot_band is None:
            return None
        top, bottom = slot_band
        y0 = float(min(top, bottom))
        y1 = float(max(top, bottom))
        x0 = float(min(slot_x0, slot_x1))
        x1 = float(max(slot_x0, slot_x1))
        if x1 <= x0 or y1 <= y0:
            return None
        return (x0, y0, x1, y1)

    @staticmethod
    def _build_source_flags(
        state: Dict[str, object],
        fallback_used: bool,
        split_band_used: bool,
        cluster_assigned: bool,
        given_detected: bool,
        explicit_mark: bool,
    ) -> Dict[str, bool]:
        return {
            "fallback": bool(state.get("fallback_used")) or fallback_used,
            "split": bool(state.get("split_used")) or split_band_used,
            "bp_label_missing": bool(state.get("bp_label_missing")),
            "hr_label_missing": bool(state.get("hr_label_missing")),
            "cluster_assigned": bool(cluster_assigned),
            "given_detected": bool(given_detected),
            "explicit_mark": bool(explicit_mark),
        }

    @staticmethod
    def _resolve_source_type(flags: Dict[str, bool]) -> str:
        if flags.get("fallback"):
            return "fallback"
        if flags.get("split"):
            return "split"
        if flags.get("cluster_assigned"):
            return "cluster"
        return "label"

    @staticmethod
    def _build_token_boxes(vitals: Optional[Dict[str, object]], due_rect: Optional[Tuple[float, float, float, float]]) -> Dict[str, List[Tuple[float, float, float, float]]]:
        boxes: Dict[str, List[Tuple[float, float, float, float]]] = {"bp": [], "hr": [], "mark": []}
        if due_rect is not None:
            boxes["mark"].append(tuple(map(float, due_rect)))
        if not isinstance(vitals, dict):
            return boxes
        bp_bbox = vitals.get("bp_bbox")
        if isinstance(bp_bbox, (list, tuple)) and len(bp_bbox) == 4:
            boxes["bp"].append(tuple(map(float, bp_bbox)))
        hr_bbox = vitals.get("hr_bbox")
        if isinstance(hr_bbox, (list, tuple)) and len(hr_bbox) == 4:
            boxes["hr"].append(tuple(map(float, hr_bbox)))
        return boxes

    def _page_render_metrics(self, page: "fitz.Page") -> Tuple[float, int, int]:
        page_index = int(getattr(page, "number", 0))
        cached = self._page_render_cache.get(page_index)
        if cached:
            return cached
        page_width = float(page.rect.width or 0.0)
        page_height = float(page.rect.height or 0.0)
        target_width = 1600.0
        scale = 1.0
        if page_width > 0:
            scale = max(1.0, target_width / page_width)
        matrix = fitz.Matrix(scale, scale) if fitz is not None else None  # type: ignore[attr-defined]
        width_px = int(round(page_width * scale)) if page_width > 0 else int(scale * 1000)
        height_px = int(round(page_height * scale)) if page_height > 0 else int(scale * 1000)
        if matrix is not None:
            try:
                pix = page.get_pixmap(matrix=matrix)
                width_px = int(pix.width)
                height_px = int(pix.height)
            except Exception:
                pass
        metrics = (scale, width_px, height_px)
        self._page_render_cache[page_index] = metrics
        return metrics

    @staticmethod
    def _rect_points_to_pixels(
        rect: Optional[Tuple[float, float, float, float]],
        scale: float,
    ) -> Optional[Tuple[float, float, float, float]]:
        if rect is None:
            return None
        x0, y0, x1, y1 = rect
        width = x1 - x0
        height = y1 - y0
        if width <= 0.0 or height <= 0.0:
            return None
        factor = float(scale) if scale > 0 else 1.0
        return (
            x0 * factor,
            y0 * factor,
            width * factor,
            height * factor,
        )

    def _rect_list_to_pixels(
        self,
        rects: Iterable[Tuple[float, float, float, float]],
        scale: float,
    ) -> List[Tuple[float, float, float, float]]:
        results: List[Tuple[float, float, float, float]] = []
        for rect in rects:
            converted = self._rect_points_to_pixels(rect, scale)
            if converted is not None:
                results.append(converted)
        return results

    @staticmethod
    def _union_rects(
        rects: Iterable[Tuple[float, float, float, float]]
    ) -> Optional[Tuple[float, float, float, float]]:
        rect_list = list(rects)
        if not rect_list:
            return None
        x0 = min(rect[0] for rect in rect_list)
        y0 = min(rect[1] for rect in rect_list)
        x1 = max(rect[0] + rect[2] for rect in rect_list)
        y1 = max(rect[1] + rect[3] for rect in rect_list)
        width = x1 - x0
        height = y1 - y0
        if width <= 0.0 or height <= 0.0:
            return None
        return (x0, y0, width, height)

    def _build_overlay_payload(
        self,
        *,
        band_rect: Optional[Tuple[float, float, float, float]],
        slot_rects: Dict[str, Optional[Tuple[float, float, float, float]]],
        token_boxes: Dict[str, List[Tuple[float, float, float, float]]],
        scale: float,
        page_width_px: int,
        page_height_px: int,
        active_slot: str,
        slot_bp: Optional[str],
        slot_hr: Optional[int],
    ) -> Dict[str, object]:
        slot_rects_px: Dict[str, Tuple[float, float, float, float]] = {}
        for key, rect in slot_rects.items():
            converted = self._rect_points_to_pixels(rect, scale)
            if converted is not None:
                slot_rects_px[str(key)] = converted
        band_rect_px = self._rect_points_to_pixels(band_rect, scale)
        bp_rects = token_boxes.get("bp") if isinstance(token_boxes, dict) else []
        hr_rects = token_boxes.get("hr") if isinstance(token_boxes, dict) else []
        mark_rects = token_boxes.get("mark") if isinstance(token_boxes, dict) else []
        bp_rects_px = self._rect_list_to_pixels(bp_rects or [], scale)
        hr_rects_px = self._rect_list_to_pixels(hr_rects or [], scale)
        mark_rects_px = self._rect_list_to_pixels(mark_rects or [], scale)
        vital_rects_px: List[Tuple[float, float, float, float]] = []
        vital_rects_px.extend(bp_rects_px)
        vital_rects_px.extend(hr_rects_px)
        vital_bbox_px = self._union_rects(vital_rects_px)

        labels: List[Dict[str, object]] = []
        if slot_bp and bp_rects_px:
            label_rect = bp_rects_px[0]
            labels.append(
                {
                    "text": f"SBP: {slot_bp}",
                    "x": label_rect[0],
                    "y": max(0.0, label_rect[1] - 18.0),
                }
            )
        if isinstance(slot_hr, int) and hr_rects_px:
            label_rect = hr_rects_px[0]
            labels.append(
                {
                    "text": f"HR: {slot_hr}",
                    "x": label_rect[0],
                    "y": max(0.0, label_rect[1] - 18.0),
                }
            )

        return {
            "page": {
                "width": int(page_width_px),
                "height": int(page_height_px),
                "scale": float(scale),
            },
            "active_slot": active_slot,
            "audit_band": band_rect_px,
            "slot_bboxes": slot_rects_px,
            "vital_bbox": vital_bbox_px,
            "vital_boxes": vital_rects_px,
            "mark_bboxes": mark_rects_px,
            "labels": labels,
        }

    @staticmethod
    def _append_anomaly(
        anomalies: List[Dict[str, object]],
        category: str,
        room_bed: str,
        slot_label: str,
        page_index: int,
        message: str,
        record_id: Optional[int],
        detail: Optional[Dict[str, object]] = None,
    ) -> None:
        entry: Dict[str, object] = {
            "category": category,
            "message": message,
            "room_bed": room_bed,
            "slot": slot_label,
            "page_index": int(page_index),
            "page_number": int(page_index) + 1,
            "record_ids": [int(record_id)] if isinstance(record_id, int) else [],
        }
        if detail:
            entry["detail"] = detail
        anomalies.append(entry)

    @staticmethod
    def _merge_counts(target: Dict[str, int], delta: Dict[str, int]) -> None:
        for key in target:
            target[key] += int(delta.get(key, 0))


def _resolve_audit_date_for_cli(pdf_path: Path) -> Tuple[date, str]:
    try:
        audit_dt, audit_text = audit_date_from_filename(pdf_path)
        return audit_dt.date(), audit_text
    except ValueError:
        audit_date = resolve_audit_date(pdf_path)
        return audit_date, format_mmddyyyy(audit_date)


def _cli_run(pdf_path: Path, hall: str, export_dir: Optional[Path]) -> int:
    audit_date, audit_date_text = _resolve_audit_date_for_cli(pdf_path)
    result = run_mar_audit(pdf_path, hall.upper(), audit_date)
    counts = dict(result.counts)

    target_dir = Path(export_dir).expanduser().resolve() if export_dir else exports_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    base_name = Path(result.source_basename).stem
    report_name = sanitize_filename(f"{result.audit_date_mmddyyyy}_{result.hall}_{base_name}.txt")
    report_path = target_dir / report_name
    write_report(
        records=result.records,
        counts=result.counts,
        audit_date_mmddyyyy=result.audit_date_mmddyyyy,
        hall=result.hall,
        source_basename=result.source_basename,
        out_path=report_path,
    )

    path_hash = hashlib.sha256(str(pdf_path).encode("utf-8")).hexdigest()
    print(
        "AUDIT_OK sha={sha} hall={hall} reviewed={reviewed} hold_miss={hm} held_appropriate={ha} "
        "compliant={comp} dcd={dcd} txt={txt}".format(
            sha=path_hash,
            hall=result.hall,
            reviewed=int(counts.get("reviewed", 0)),
            hm=int(counts.get("hold_miss", 0)),
            ha=int(counts.get("held_appropriate", 0)),
            comp=int(counts.get("compliant", 0)),
            dcd=int(counts.get("dcd", 0)),
            txt=report_path.name,
        )
    )
    if result.qa_paths:
        print(f"QA_IMAGES count={len(result.qa_paths)}", flush=True)
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Headless AuditWorker runner")
    parser.add_argument("pdf", type=Path, help="Path to the MAR PDF to audit")
    parser.add_argument("--hall", default="UNKNOWN", help="Hall identifier (default: UNKNOWN)")
    parser.add_argument("--export-dir", type=Path, help="Optional export directory override")
    args = parser.parse_args(list(argv) if argv is not None else None)

    pdf_path = args.pdf.expanduser().resolve()
    if not pdf_path.exists():
        parser.error(f"{pdf_path} not found")
    return _cli_run(pdf_path, str(args.hall).upper(), args.export_dir)


if __name__ == "__main__":
    raise SystemExit(main())
