"""Headless audit runner used by the CLI and acceptance tooling."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from hushdesk.fs.exports import exports_dir, sanitize_filename
from hushdesk.logs.rotating import get_logger, log_path
from hushdesk.pdf.dates import dev_override_date, format_mmddyyyy, resolve_audit_date
from hushdesk.pdf.mar_header import audit_date_from_filename
from hushdesk.pdf.mar_parser_mupdf import MarAuditResult, run_mar_audit
from hushdesk.report.txt_writer import write_report

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class HeadlessOptions:
    """Configuration for a headless audit run."""

    input_pdf: Path
    hall: Optional[str] = None
    audit_date: Optional[date] = None
    qa_png: Optional[str] = None
    log_dir: Path = field(default_factory=lambda: Path("debug"))
    log_file: Optional[Path] = None
    trace: bool = False


@dataclass(slots=True)
class HeadlessResult:
    """Outcome of a headless audit run."""

    exit_code: int
    txt_path: Optional[Path]
    counts: Dict[str, int]
    logs: List[str]
    warnings: List[str]
    summary_line: str
    audit_label: Optional[str]
    qa_png: Optional[Path]
    qa_paths: List[Path]
    log_file: Path


def execute_headless(options: HeadlessOptions) -> HeadlessResult:
    """Run the audit pipeline headlessly with ``options``."""

    input_pdf = options.input_pdf.expanduser().resolve()
    if not input_pdf.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_pdf}")

    log_dir = options.log_dir.expanduser().resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = (options.log_file or (log_dir / _default_log_name())).expanduser().resolve()

    base_logger = _configure_logging(log_file, trace=options.trace)
    hall_value = (options.hall or "UNKNOWN").upper()
    LOGGER.info("Headless start: %s", input_pdf)
    LOGGER.info("Headless hall: %s", hall_value)
    if base_logger is not None and options.trace:
        base_logger.debug("Trace mode enabled for headless execution.")

    rotation_target = log_path()
    print(f"LOG_ROTATION_OK path={rotation_target}", flush=True)

    print("PDF Engine: pymupdf", flush=True)

    audit_date, audit_label_base = _determine_audit_date(input_pdf, options.audit_date)

    try:
        audit_result = run_mar_audit(
            input_pdf,
            hall_value,
            audit_date,
            qa_prefix=options.qa_png,
        )
    except Exception:  # pragma: no cover - defensive guard
        LOGGER.exception("Headless audit raised an unexpected error")
        return HeadlessResult(
            exit_code=1,
            txt_path=None,
            counts={},
            logs=[],
            warnings=["MAR parser failed; see logs for details"],
            summary_line="ERROR — headless audit failed",
            audit_label=f"{format_mmddyyyy(audit_date)} — {hall_value}",
            qa_png=None,
            qa_paths=[],
            log_file=log_file,
        )

    export_dir = exports_dir()
    export_dir.mkdir(parents=True, exist_ok=True)

    report_path = _write_txt_report(audit_result, export_dir)

    audit_label = f"{audit_label_base} — {audit_result.hall or hall_value}"

    summary_line = audit_result.summary_line or _build_summary_line(
        audit_result.counts,
        audit_label,
        audit_result.blocks,
        audit_result.tracks,
    )

    logs: List[str] = []
    if audit_result.instrument_line:
        logs.append(audit_result.instrument_line)
    logs.append(summary_line)

    exit_code = 0 if audit_result.records else 2
    LOGGER.info("Headless run completed exit_code=%s txt=%s", exit_code, report_path)

    return HeadlessResult(
        exit_code=exit_code,
        txt_path=report_path,
        counts=dict(audit_result.counts),
        logs=logs,
        warnings=[],
        summary_line=summary_line,
        audit_label=audit_label,
        qa_png=audit_result.qa_paths[0] if audit_result.qa_paths else None,
        qa_paths=list(audit_result.qa_paths),
        log_file=log_file,
    )


def _configure_logging(log_file: Path, *, trace: bool = False) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    base_logger = get_logger()
    level = logging.DEBUG if trace else logging.INFO
    base_logger.setLevel(level)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not any(isinstance(handler, logging.StreamHandler) for handler in root_logger.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(level)
        root_logger.addHandler(stream_handler)

    existing_paths = {
        getattr(handler, "baseFilename", None)
        for handler in base_logger.handlers
        if hasattr(handler, "baseFilename")
    }
    if str(log_file) not in existing_paths:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        base_logger.addHandler(file_handler)

    return base_logger


def _build_summary_line(
    counts: Dict[str, int],
    audit_label: Optional[str],
    blocks: int,
    tracks: int,
) -> str:
    reviewed = counts.get("reviewed", 0)
    hold_miss = counts.get("hold_miss", 0)
    held_app = counts.get("held_appropriate", 0)
    compliant = counts.get("compliant", 0)
    dcd = counts.get("dcd", 0)
    label = audit_label or "Date unknown"
    date_token = label.split("—", 1)[0].strip()
    if not date_token or date_token.lower().startswith("audit"):
        date_token = "unknown"
    return (
        f"Blocks:{blocks} Tracks:{tracks} Date:{date_token} Reviewed:{reviewed} "
        f"Hold-Miss:{hold_miss} Held-Appropriate:{held_app} Compliant:{compliant} DC'D:{dcd}"
    )


def _default_log_name() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"headless_{timestamp}.log"


def _determine_audit_date(input_pdf: Path, explicit: Optional[date]) -> tuple[date, str]:
    if explicit is not None:
        formatted = format_mmddyyyy(explicit)
        return explicit, formatted

    override = dev_override_date()
    if override is not None:
        formatted = format_mmddyyyy(override)
        return override, formatted

    try:
        audit_dt, label = audit_date_from_filename(input_pdf)
        return audit_dt.date(), label
    except ValueError:
        resolved = resolve_audit_date(input_pdf)
        formatted = format_mmddyyyy(resolved)
        return resolved, formatted


def _write_txt_report(audit_result: MarAuditResult, export_dir: Path) -> Path:
    base_name = Path(audit_result.source_basename).stem or "HushDesk"
    report_name = sanitize_filename(
        f"{audit_result.audit_date_mmddyyyy}_{audit_result.hall}_{base_name}.txt"
    )
    report_path = export_dir / report_name
    return write_report(
        records=audit_result.records,
        counts=audit_result.counts,
        audit_date_mmddyyyy=audit_result.audit_date_mmddyyyy,
        hall=audit_result.hall,
        source_basename=audit_result.source_basename,
        out_path=report_path,
    )


__all__ = ["HeadlessOptions", "HeadlessResult", "execute_headless"]
