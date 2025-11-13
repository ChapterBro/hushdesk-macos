"""Engine-level audit helpers that wrap the canonical MAR parser."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Optional

from hushdesk.pdf.dates import dev_override_date, resolve_audit_date
from hushdesk.pdf.mar_header import audit_date_from_filename
from hushdesk.pdf.mar_parser_mupdf import MarAuditResult, run_mar_audit as _legacy_run


@dataclass(slots=True)
class AuditContext:
    """Parameters for an engine-level MAR audit run."""

    pdf_path: str | Path
    hall: str = "UNKNOWN"
    audit_date: Optional[date] = None
    qa_prefix: Optional[str | bool] = False
    debug: bool = False


@dataclass(slots=True)
class EngineAuditResult:
    """Summarized result from the MAR audit engine."""

    ok: bool
    counts: Dict[str, int]
    error: Optional[str] = None
    result: Optional[MarAuditResult] = None


def _auto_audit_date(pdf_path: Path, requested: Optional[date]) -> date:
    if requested:
        return requested
    override = dev_override_date()
    if override:
        return override
    try:
        audit_dt, _ = audit_date_from_filename(pdf_path)
        return audit_dt.date()
    except Exception:
        return resolve_audit_date(pdf_path)


def _counts_from_result(result: MarAuditResult) -> Dict[str, int]:
    instrumentation = dict(result.instrumentation or {})
    counts = dict(result.counts or {})
    pages_total = (
        instrumentation.get("pages_total")
        or instrumentation.get("pages")
        or result.pages_total
        or 0
    )
    pages_with_band = instrumentation.get("pages_with_band") or result.pages_with_band or 0
    due_total = instrumentation.get("due") or counts.get("due") or counts.get("vitals") or 0
    rules_total = (
        instrumentation.get("parametered")
        or counts.get("parametered")
        or counts.get("rules")
        or 0
    )
    summary = {
        "pages": int(pages_total),
        "bands": int(pages_with_band),
        "vitals": int(due_total),
        "rules": int(rules_total),
        "decisions": int(len(result.records or [])),
    }
    for key, value in counts.items():
        summary.setdefault(key, value)
    return summary


def run_mar_audit(context: AuditContext) -> EngineAuditResult:
    """Execute the MAR audit engine with ``context``."""

    pdf_path = Path(context.pdf_path).expanduser().resolve()
    if not pdf_path.exists():
        return EngineAuditResult(
            ok=False,
            counts={},
            error=f"FileNotFoundError: {pdf_path}",
        )

    hall = (context.hall or "UNKNOWN").upper()
    audit_date = _auto_audit_date(pdf_path, context.audit_date)

    try:
        result = _legacy_run(
            pdf_path,
            hall,
            audit_date,
            qa_prefix=context.qa_prefix,
        )
    except Exception as exc:
        return EngineAuditResult(
            ok=False,
            counts={},
            error=f"{exc.__class__.__name__}: {exc}",
        )

    counts = _counts_from_result(result)
    return EngineAuditResult(ok=True, counts=counts, result=result)


__all__ = ["AuditContext", "EngineAuditResult", "run_mar_audit"]
