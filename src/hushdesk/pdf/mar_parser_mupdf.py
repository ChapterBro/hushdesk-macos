"""Canonical MAR parser driven by MuPDF extracted coordinates."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from hushdesk.fs.exports import resolve_qa_prefix
from hushdesk.pdf.dates import format_mmddyyyy
from hushdesk.pdf.mar_blocks import draw_med_blocks_debug
from hushdesk.pdf import mar_grid_extract as grid_extract
from hushdesk.pdf.mar_grid_extract import DueRecord, PageExtraction, extract_pages
from hushdesk.pdf.mar_header import band_for_date
from hushdesk.pdf.mupdf_canon import CanonPage, iter_canon_pages
from hushdesk.pdf.qa_overlay import QAHighlights, draw_overlay
from hushdesk.report.model import DecisionRecord

ALLOWED_CODES = {4, 6, 11, 12, 15}


@dataclass(slots=True)
class MarAuditResult:
    """Outcome of ``run_mar_audit``."""

    records: List[DecisionRecord]
    counts: Dict[str, int]
    instrumentation: dict[str, object]
    blocks: int
    tracks: int
    audit_date_mmddyyyy: str
    hall: str
    source_basename: str
    qa_paths: List[Path] = field(default_factory=list)
    due_records: List[DueRecord] = field(default_factory=list)
    summary_line: str = ""
    instrument_line: str = ""
    pages_total: int = 0
    pages_with_band: int = 0
    suppressed: int = 0


@dataclass(slots=True)
class RuleEntry:
    """Strict hold rule paired with the captured vital."""

    vital: str
    comparator: str
    threshold: int
    value: Optional[int]
    value_text: str
    rule_text: str


def run_mar_audit(
    pdf_path: str | Path,
    hall: str,
    audit_date: date,
    qa_prefix: str | Path | bool | None = None,
) -> MarAuditResult:
    """Run the canonical MuPDF MAR parser against ``pdf_path``."""

    source_path = Path(pdf_path).expanduser().resolve()
    hall_value = hall.upper()
    audit_date_text = format_mmddyyyy(audit_date)
    qa_dir: Path | None = None
    qa_file: Path | None = None

    if qa_prefix is False:
        print("QA_OVERLAY_SKIP reason=disabled", flush=True)
    else:
        try:
            resolved = resolve_qa_prefix(qa_prefix)  # type: ignore[arg-type]
            resolved_path = Path(resolved)
            if resolved_path.suffix.lower() == ".png":
                qa_file = resolved_path
                qa_dir = resolved_path.parent
            else:
                qa_dir = resolved_path
            source_hint = qa_prefix if qa_prefix else "default"
            print(
                f"QA_OVERLAY_DEST resolved={resolved_path} source={source_hint}",
                flush=True,
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            print(f"QA_OVERLAY_SKIP reason={exc.__class__.__name__}: {exc}", flush=True)
            qa_dir = None
            qa_file = None

    pages = list(iter_canon_pages(source_path))
    pages_total, pages_with_band = _coverage_from_pages(pages, audit_date)
    extractions = extract_pages(pages, audit_date, hall_value)
    suppressed = getattr(grid_extract, "telemetry_suppressed", 0)

    records: List[DecisionRecord] = []
    counts = _empty_counts()
    all_due_records: List[DueRecord] = []
    qa_paths: List[Path] = []
    nonchip_breakdown: Dict[str, int] = {"other_code": 0, "empty": 0}
    rooms_resolved = 0
    rooms_fallback = 0

    for extraction in extractions:
        all_due_records.extend(extraction.records)
        for due in extraction.records:
            if due.room and due.room != "UNKNOWN":
                rooms_resolved += 1
            else:
                rooms_fallback += 1
            due_decisions = _decisions_for_due(
                due,
                audit_date_text,
                hall_value,
                source_path.name,
            )
            if due.parametered and not any(decision.chip for decision in due_decisions):
                category = due.mark_category or "unknown"
                nonchip_breakdown[category] = nonchip_breakdown.get(category, 0) + 1
            for decision in due_decisions:
                _tally(decision, counts)
            records.extend(due_decisions)

        if qa_dir is not None:
            if extraction.highlights:
                overlay_hint: Path = qa_file if qa_file and not qa_paths else qa_dir
                overlay_path = draw_overlay(
                    extraction.page.pixmap,
                    extraction.highlights,
                    qa_prefix=overlay_hint,
                )
                if overlay_path is not None:
                    qa_paths.append(overlay_path)
            block_path = draw_med_blocks_debug(extraction.page, extraction.blocks, qa_dir)
            if block_path is not None:
                qa_paths.append(block_path)

    instrumentation = _instrumentation_metrics(extractions, all_due_records)
    instrumentation["suppressed"] = suppressed
    counts["parametered"] = int(instrumentation.get("parametered", 0))
    counts["no_rule"] = int(instrumentation.get("no_rule", 0))
    counts["no_sbp"] = int(instrumentation.get("no_sbp", 0))
    counts["no_hr"] = int(instrumentation.get("no_hr", 0))
    counts["reviewed"] = (
        counts["hold_miss"]
        + counts["held_appropriate"]
        + counts["compliant"]
        + counts["dcd"]
    )

    parametered_total = int(instrumentation.get("parametered", counts["parametered"]))
    other_code = int(nonchip_breakdown.get("other_code", 0))
    empty = int(nonchip_breakdown.get("empty", 0))
    nonchip = other_code + empty
    instrumentation["parametered_total"] = parametered_total
    instrumentation["parametered"] = parametered_total
    instrumentation["other_code"] = other_code
    instrumentation["empty"] = empty
    instrumentation["nonchip"] = nonchip
    instrumentation["nonchip_breakdown"] = {
        "other_code": other_code,
        "empty": empty,
    }
    instrumentation["nonchip_record_delta"] = parametered_total - counts["reviewed"]
    instrumentation["pages_total"] = pages_total
    instrumentation["pages_with_band"] = pages_with_band
    extra_nonchip_categories = {
        key: value
        for key, value in nonchip_breakdown.items()
        if key not in {"other_code", "empty"} and value
    }
    if extra_nonchip_categories:
        instrumentation["nonchip_breakdown_extra"] = extra_nonchip_categories

    instrument_line = _format_instrument_line(audit_date_text, instrumentation)
    if instrument_line:
        print(instrument_line, flush=True)

    hall_candidates = {
        record.hall.upper()
        for record in all_due_records
        if record.hall and record.hall.upper() != "UNKNOWN"
    }
    if hall_candidates:
        if len(hall_candidates) == 1:
            hall_value = next(iter(hall_candidates))
        else:
            hall_value = "MIXED"

    print(
        f"SCOPE_OK hall={hall_value} date={audit_date_text} pages={pages_total} "
        f"bands={pages_with_band}",
        flush=True,
    )

    blocks = sum(len(extraction.blocks) for extraction in extractions)
    tracks = len(all_due_records)

    print(f"SLOT_OK tracks={tracks} parametered={counts['parametered']}", flush=True)

    if not records:
        print("DEPENDENCY_MISS sprint=6")

    summary_line = (
        f"Blocks:{blocks} Tracks:{tracks} Date:{audit_date_text} Reviewed:{counts['reviewed']}"
        f" Hold-Miss:{counts['hold_miss']} Held-Appropriate:{counts['held_appropriate']}"
        f" Compliant:{counts['compliant']} DC'D:{counts['dcd']}"
    )
    dc_columns = grid_extract.dc_column_totals()
    print(
        f"DC_OK hold_miss={counts['hold_miss']} held_app={counts['held_appropriate']}"
        f" compliant={counts['compliant']} dcd={counts['dcd']} columns={dc_columns}",
        flush=True,
    )
    print(f'ROOM_OK rooms_resolved={rooms_resolved} fallback={rooms_fallback}', flush=True)
    merged_before, merged_after = grid_extract.dedup_totals()
    duplicates_removed = max(0, merged_before - merged_after)
    print(
        f"DEDUP_OK merged={merged_before}->{merged_after} duplicates_removed={duplicates_removed}",
        flush=True,
    )
    print(f"RULE_GATE_OK param_only=true suppressed={suppressed}", flush=True)
    preview_meta_entries = [record.preview for record in records if isinstance(record.preview, dict)]
    roi_sizes: List[Tuple[float, float]] = []
    for meta in preview_meta_entries:
        roi = meta.get("roi") if isinstance(meta, dict) else None
        if not isinstance(roi, (list, tuple)) or len(roi) < 4:
            continue
        try:
            roi_width = float(roi[2])
            roi_height = float(roi[3])
        except (TypeError, ValueError):
            continue
        roi_sizes.append((roi_width, roi_height))
    roi_count = len(roi_sizes)
    avg_roi_width = int(round(sum(width for width, _ in roi_sizes) / roi_count)) if roi_count else 0
    avg_roi_height = int(round(sum(height for _, height in roi_sizes) / roi_count)) if roi_count else 0
    print(
        f"PREVIEW_META_OK items={len(records)} with_roi={roi_count} avg_roi={avg_roi_width}x{avg_roi_height}",
        flush=True,
    )
    result = MarAuditResult(
        records=records,
        counts=counts,
        instrumentation=instrumentation,
        blocks=blocks,
        tracks=tracks,
        audit_date_mmddyyyy=audit_date_text,
        hall=hall_value,
        source_basename=source_path.name,
        qa_paths=qa_paths,
        due_records=all_due_records,
        summary_line=summary_line,
        instrument_line=instrument_line,
        pages_total=pages_total,
        pages_with_band=pages_with_band,
        suppressed=suppressed,
    )
    return result


def _dose_for_slot(normalized_slot: str) -> str:
    token = normalized_slot.lower()
    if token in {"6a-10", "0800", "am"}:
        return "AM"
    if token in {"pm", "hs", "1900", "4pm-7"}:
        return "PM"
    if token == "12p-2":
        return "PM"
    return "AM"


def _empty_counts() -> Dict[str, int]:
    return {
        "reviewed": 0,
        "parametered": 0,
        "no_rule": 0,
        "no_sbp": 0,
        "no_hr": 0,
        "hold_miss": 0,
        "held_appropriate": 0,
        "compliant": 0,
        "dcd": 0,
    }


def _instrumentation_metrics(
    extractions: Sequence[PageExtraction],
    due_records: Sequence[DueRecord],
) -> dict[str, object]:
    pages = len(extractions)
    due_total = len(due_records)
    parametered = sum(1 for due in due_records if due.parametered)
    no_rule = max(due_total - parametered, 0)
    no_sbp = sum(
        1
        for due in due_records
        if due.parametered and _has_sbp_rule(due.rules) and due.sbp is None
    )
    no_hr = sum(
        1
        for due in due_records
        if due.parametered and _has_hr_rule(due.rules) and due.hr is None
    )
    return {
        "pages": pages,
        "due": due_total,
        "parametered": parametered,
        "no_rule": no_rule,
        "no_sbp": no_sbp,
        "no_hr": no_hr,
    }


def _coverage_from_pages(
    pages: Sequence[CanonPage],
    audit_date: date,
    *,
    band_resolver: Callable[[CanonPage, date], Optional[Tuple[float, float]]] = band_for_date,
) -> tuple[int, int]:
    total = len(pages)
    with_band = 0
    for page in pages:
        try:
            band = band_resolver(page, audit_date)
        except Exception:  # pragma: no cover - defensive guard
            band = None
        if band:
            with_band += 1
    return total, with_band


@dataclass(slots=True)
class _CoverageProbe:
    """Test helper to validate coverage calculations over synthetic pages."""

    total: int
    with_band: int

    def __call__(self) -> tuple[int, int]:
        class _ProbePage:
            __slots__ = ("has_band",)

            def __init__(self, has_band: bool) -> None:
                self.has_band = has_band

        pages = [_ProbePage(index < self.with_band) for index in range(self.total)]

        def _stub_band(page: object, _: date) -> Optional[Tuple[float, float]]:
            return (0.0, 1.0) if getattr(page, "has_band", False) else None

        return _coverage_from_pages(pages, date.today(), band_resolver=_stub_band)


def _tally(record: DecisionRecord, counts: Dict[str, int]) -> None:
    if not record.chip:
        return
    kind = record.kind
    if kind == "HOLD-MISS":
        counts["hold_miss"] += 1
    elif kind == "HELD-APPROPRIATE":
        counts["held_appropriate"] += 1
    elif kind == "COMPLIANT":
        counts["compliant"] += 1
    elif kind == "DC'D":
        counts["dcd"] += 1


def _format_instrument_line(audit_date_mmddyyyy: str, metrics: dict[str, object]) -> str:
    if not metrics:
        return ""
    return (
        f"INSTRUMENT date={audit_date_mmddyyyy} pages={metrics.get('pages', 0)}"
        f" due={metrics.get('due', 0)} parametered={metrics.get('parametered', 0)}"
        f" nonchip={metrics.get('nonchip', 0)}"
        f" other_code={metrics.get('other_code', 0)} empty={metrics.get('empty', 0)}"
    )

def _decisions_for_due(
    due: DueRecord,
    audit_date_mmddyyyy: str,
    default_hall: str,
    source_basename: str,
) -> List[DecisionRecord]:
    hall_value = (due.hall or default_hall).upper()
    room = due.room or "UNKNOWN"
    dose = _dose_for_slot(due.normalized_slot)
    entries = _rule_entries(due)
    state_detail = _state_detail(due)

    extras_base: Dict[str, object] = {
        "page_index": due.page_index,
        "time_slot": due.time_slot,
        "slot_id": due.slot_id,
        "normalized_slot": due.normalized_slot,
        "state": due.state,
        "sbp": due.sbp,
        "hr": due.hr,
        "code": due.code,
        "audit_band": due.audit_band,
        "track_band": due.track_band,
        "bp_bbox": due.bp_bbox,
        "hr_bbox": due.hr_bbox,
        "due_bbox": due.due_bbox,
        "bp_text": due.bp_text,
        "hr_text": due.hr_text,
        "due_text": due.due_text,
        "rule_text_raw": due.rule_text,
        "rules": due.rules.as_dict(),
    }

    records: List[DecisionRecord] = []
    preview_meta = _preview_payload_for_due(due)

    is_parametered = due.parametered

    if due.state == "DCD":
        records.append(
            _build_record(
                hall=hall_value,
                audit_date_mmddyyyy=audit_date_mmddyyyy,
                source_basename=source_basename,
                room=room,
                dose=dose,
                kind="DC'D",
                rule_text="Due cell DC'd",
                vital_text="",
                state_detail="dc'd",
                code=None,
                dcd_reason="X mark",
                chip=is_parametered,
                extras_base=extras_base,
                entry_extras={"rule_entries": [entry.rule_text for entry in entries]},
                preview=preview_meta,
            )
        )
        return records

    if due.state == "CODE":
        if due.code in ALLOWED_CODES:
            if not entries:
                records.append(
                    _fallback_record(
                        hall=hall_value,
                        audit_date_mmddyyyy=audit_date_mmddyyyy,
                        source_basename=source_basename,
                        room=room,
                        dose=dose,
                        kind="HELD-APPROPRIATE",
                        state_detail=f"code {due.code}",
                        extras_base=extras_base,
                        code=due.code,
                        message="Hold if strict rule documented",
                        chip=is_parametered,
                        preview=preview_meta,
                    )
                )
                return records
            for entry in entries:
                triggered = _rule_triggered(entry.comparator, entry.threshold, entry.value)
                records.append(
                    _build_record(
                        hall=hall_value,
                        audit_date_mmddyyyy=audit_date_mmddyyyy,
                        source_basename=source_basename,
                        room=room,
                        dose=dose,
                        kind="HELD-APPROPRIATE",
                        rule_text=entry.rule_text,
                        vital_text=entry.value_text,
                        state_detail=f"code {due.code}",
                        code=due.code,
                        dcd_reason=None,
                        chip=is_parametered,
                        extras_base=extras_base,
                        entry_extras={
                            "rule_vital": entry.vital,
                            "threshold": entry.threshold,
                            "triggered": triggered,
                            "state_detail": state_detail,
                        },
                        preview=preview_meta,
                    )
                )
            return records

        # Disallowed numeric codes ⇒ reviewed without chip credit.
        if not entries:
            records.append(
                _fallback_record(
                    hall=hall_value,
                    audit_date_mmddyyyy=audit_date_mmddyyyy,
                    source_basename=source_basename,
                    room=room,
                    dose=dose,
                    kind="COMPLIANT",
                    state_detail=f"code {due.code}",
                    extras_base=extras_base,
                    code=due.code,
                    message="Hold if strict rule documented",
                    chip=False,
                    extra_flags={"out_of_scope": True},
                    preview=preview_meta,
                )
            )
            return records

        for entry in entries:
            triggered = _rule_triggered(entry.comparator, entry.threshold, entry.value)
            records.append(
                _build_record(
                    hall=hall_value,
                    audit_date_mmddyyyy=audit_date_mmddyyyy,
                    source_basename=source_basename,
                    room=room,
                    dose=dose,
                    kind="COMPLIANT",
                    rule_text=entry.rule_text,
                    vital_text=entry.value_text,
                    state_detail=f"code {due.code}",
                    code=due.code,
                    dcd_reason=None,
                    chip=False,
                    extras_base=extras_base,
                    entry_extras={
                        "rule_vital": entry.vital,
                        "threshold": entry.threshold,
                        "triggered": triggered,
                        "out_of_scope": True,
                        "state_detail": state_detail,
                    },
                    preview=preview_meta,
                )
            )
        return records

    # GIVEN / EMPTY / other observational states
    if not entries:
        records.append(
            _fallback_record(
                hall=hall_value,
                audit_date_mmddyyyy=audit_date_mmddyyyy,
                source_basename=source_basename,
                room=room,
                dose=dose,
                kind="COMPLIANT",
                state_detail=state_detail,
                extras_base=extras_base,
                code=None,
                message="Hold if strict rule documented",
                chip=False,
                preview=preview_meta,
                )
            )
        return records

    is_given = due.state == "GIVEN"
    for entry in entries:
        triggered = _rule_triggered(entry.comparator, entry.threshold, entry.value)
        kind = "HOLD-MISS" if triggered else "COMPLIANT"
        records.append(
            _build_record(
                hall=hall_value,
                audit_date_mmddyyyy=audit_date_mmddyyyy,
                source_basename=source_basename,
                room=room,
                dose=dose,
                kind=kind,
                rule_text=entry.rule_text,
                vital_text=entry.value_text,
                state_detail=state_detail,
                code=None,
                dcd_reason=None,
                chip=is_parametered and is_given,
                extras_base=extras_base,
                entry_extras={
                    "rule_vital": entry.vital,
                    "threshold": entry.threshold,
                    "triggered": triggered,
                    "state_detail": state_detail,
                },
                preview=preview_meta,
            )
        )
    return records


def _rule_entries(due: DueRecord) -> List[RuleEntry]:
    entries: List[RuleEntry] = []
    rules = due.rules
    if not rules.strict:
        return entries

    if rules.sbp_lt is not None:
        entries.append(
            RuleEntry(
                vital="SBP",
                comparator="<",
                threshold=rules.sbp_lt,
                value=due.sbp,
                value_text=_sbp_value_text(due),
                rule_text=f"Hold if SBP < {rules.sbp_lt}",
            )
        )
    if rules.sbp_gt is not None:
        entries.append(
            RuleEntry(
                vital="SBP",
                comparator=">",
                threshold=rules.sbp_gt,
                value=due.sbp,
                value_text=_sbp_value_text(due),
                rule_text=f"Hold if SBP > {rules.sbp_gt}",
            )
        )
    if rules.hr_lt is not None:
        entries.append(
            RuleEntry(
                vital="HR",
                comparator="<",
                threshold=rules.hr_lt,
                value=due.hr,
                value_text=_hr_value_text(due),
                rule_text=f"Hold if HR < {rules.hr_lt}",
            )
        )
    if rules.hr_gt is not None:
        entries.append(
            RuleEntry(
                vital="HR",
                comparator=">",
                threshold=rules.hr_gt,
                value=due.hr,
                value_text=_hr_value_text(due),
                rule_text=f"Hold if HR > {rules.hr_gt}",
            )
        )
    return entries


def _state_detail(due: DueRecord) -> str:
    label = due.time_slot.strip() or due.normalized_slot.upper()
    normalized = label.upper()
    if due.state == "GIVEN":
        return f"given {normalized}"
    if due.state == "CODE":
        if due.code is not None:
            return f"code {due.code}"
        return "code missing"
    if due.state == "DCD":
        return "dc'd"
    return "no mark"


def _sbp_value_text(due: DueRecord) -> str:
    text = due.bp_text.strip()
    if text:
        return f"BP {text}"
    if due.sbp is not None:
        return f"SBP {due.sbp}"
    return "SBP missing"


def _hr_value_text(due: DueRecord) -> str:
    text = due.hr_text.strip()
    if due.hr is not None:
        return f"HR {due.hr}"
    if text:
        return f"HR {text}"
    return "HR missing"


def _preview_payload_for_due(due: DueRecord) -> Optional[Dict[str, object]]:
    page_width, page_height = due.page_pixels if isinstance(due.page_pixels, tuple) else (0, 0)
    width = int(page_width) if page_width else 0
    height = int(page_height) if page_height else 0
    if width <= 0 or height <= 0:
        return None
    roi_values = due.roi_pixels
    payload: Dict[str, object] = {
        "page_index": due.page_index,
        "image_size": [width, height],
        "slot": due.normalized_slot or due.time_slot,
        "slot_id": due.slot_id,
        "recommended_fit": "Region" if roi_values else "FitWidth",
    }
    if roi_values:
        payload["roi"] = [float(component) for component in roi_values]
    return payload


def _build_record(
    *,
    hall: str,
    audit_date_mmddyyyy: str,
    source_basename: str,
    room: str,
    dose: str,
    kind: str,
    rule_text: str,
    vital_text: str,
    state_detail: str,
    code: Optional[int],
    dcd_reason: Optional[str],
    chip: bool,
    extras_base: Dict[str, object],
    entry_extras: Optional[Dict[str, object]] = None,
    preview: Optional[Dict[str, object]] = None,
) -> DecisionRecord:
    extras = dict(extras_base)
    extras["state_detail"] = state_detail
    extras["rule_text_normalized"] = rule_text
    extras["vital_text_normalized"] = vital_text
    if entry_extras:
        extras.update(entry_extras)
    return DecisionRecord(
        hall=hall,
        date_mmddyyyy=audit_date_mmddyyyy,
        source_basename=source_basename,
        room_bed=room,
        dose=dose,
        kind=kind,  # type: ignore[arg-type]
        rule_text=rule_text,
        vital_text=vital_text,
        code=code,
        dcd_reason=dcd_reason,
        notes=None,
        extras=extras,
        chip=chip,
        preview=dict(preview) if isinstance(preview, dict) else None,
    )


def _fallback_record(
    *,
    hall: str,
    audit_date_mmddyyyy: str,
    source_basename: str,
    room: str,
    dose: str,
    kind: str,
    state_detail: str,
    extras_base: Dict[str, object],
    code: Optional[int],
    message: str,
    chip: bool,
    extra_flags: Optional[Dict[str, object]] = None,
    preview: Optional[Dict[str, object]] = None,
) -> DecisionRecord:
    flags = dict(extra_flags or {})
    flags["fallback"] = True
    return _build_record(
        hall=hall,
        audit_date_mmddyyyy=audit_date_mmddyyyy,
        source_basename=source_basename,
        room=room,
        dose=dose,
        kind=kind,
        rule_text=message,
        vital_text="Rule missing",
        state_detail=state_detail,
        code=code,
        dcd_reason=None,
        chip=chip,
        extras_base=extras_base,
        entry_extras=flags,
        preview=preview,
    )


def _rule_triggered(comparator: str, threshold: int, value: Optional[int]) -> bool:
    if value is None:
        return False
    if comparator == ">":
        return value > threshold
    if comparator == "<":
        return value < threshold
    return False


def _has_sbp_rule(rules: object) -> bool:
    return getattr(rules, "sbp_lt", None) is not None or getattr(rules, "sbp_gt", None) is not None


def _has_hr_rule(rules: object) -> bool:
    return getattr(rules, "hr_lt", None) is not None or getattr(rules, "hr_gt", None) is not None


__all__ = ["MarAuditResult", "run_mar_audit"]
