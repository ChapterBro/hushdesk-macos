#!/usr/bin/env python3
"""Headless tracer that runs the audit worker pipeline on MAR PDFs."""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

from hushdesk.pdf.dates import dev_override_date, resolve_audit_date
from hushdesk.pdf.mar_header import audit_date_from_filename
from hushdesk.pdf.mar_parser_mupdf import run_mar_audit
from hushdesk.ui import preview_renderer as preview_renderer_module
from hushdesk.workers import audit_worker as audit_worker_module

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[1]
BATON_PATH = REPO_ROOT / "docs" / "BATON.md"


def _resolve_audit_date(pdf_path: Path) -> _dt.date:
    override = dev_override_date()
    if override:
        return override
    try:
        audit_dt, _ = audit_date_from_filename(pdf_path)
    except Exception:
        return resolve_audit_date(pdf_path)
    return audit_dt.date()


def _counts_from_result(result) -> Dict[str, int]:
    instrumentation = dict(result.instrumentation or {})
    counts = dict(result.counts or {})
    return {
        "pages": int(instrumentation.get("pages_total") or instrumentation.get("pages") or 0),
        "bands": int(instrumentation.get("pages_with_band") or 0),
        "vitals": int(instrumentation.get("due") or 0),
        "rules": int(instrumentation.get("parametered") or counts.get("parametered", 0) or 0),
        "decisions": int(len(result.records or [])),
    }


def _module_digest(module) -> str:
    path = Path(getattr(module, "__file__", "") or "")
    try:
        data = path.read_bytes()
    except Exception:
        return "unknown"
    return hashlib.sha256(data).hexdigest()[:12]


def _next_baton_index(text: str) -> int:
    matches = re.findall(r"^\s*(\d+)\.", text, flags=re.MULTILINE)
    numbers = [int(value) for value in matches]
    return max(numbers) + 1 if numbers else 1


def _append_baton_entry(results: List[Dict[str, Any]]) -> None:
    BATON_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = BATON_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing = "# Baton Log\n"
        BATON_PATH.write_text(existing, encoding="utf-8")
    index = _next_baton_index(existing)
    timestamp = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    worker_sha = _module_digest(audit_worker_module)
    renderer_sha = _module_digest(preview_renderer_module)
    lines = [
        "",
        f"{index}. {timestamp} — audit tracer",
        f"   - worker_sha={worker_sha} renderer_sha={renderer_sha}",
    ]
    for item in results:
        counts = item.get("counts") or {}
        status = item.get("status")
        path_hash = item.get("path_hash")
        lines.append(f"   - path_hash={path_hash} status={status} counts={counts}")
    with BATON_PATH.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def trace_pdf(pdf_path: str, *, hall: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "path_hash": hashlib.sha256(str(Path(pdf_path).expanduser().resolve()).encode("utf-8")).hexdigest(),
        "status": "FAIL",
        "counts": {"pages": 0, "bands": 0, "vitals": 0, "rules": 0, "decisions": 0},
        "error": None,
    }
    try:
        source = Path(pdf_path).expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        result["error"] = f"{exc.__class__.__name__}: {exc}"
        return result

    try:
        audit_date = _resolve_audit_date(source)
        audit_result = run_mar_audit(
            source,
            hall,
            audit_date,
            qa_prefix=False,
        )
        result["counts"] = _counts_from_result(audit_result)
        result["status"] = "OK"
    except Exception as exc:  # pragma: no cover - defensive trace capture
        result["error"] = f"{exc.__class__.__name__}: {exc}"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", nargs="+", help="Path(s) to MAR PDFs")
    parser.add_argument("--hall", default="UNKNOWN", help="Hall override for worker run")
    args = parser.parse_args(argv)

    summaries: List[Dict[str, Any]] = []
    for path in args.pdf:
        summary = trace_pdf(path, hall=args.hall)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)

    if summaries:
        _append_baton_entry(summaries)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
