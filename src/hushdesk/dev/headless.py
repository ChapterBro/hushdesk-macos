"""Headless CLI entrypoint for running the HushDesk BP audit pipeline."""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional

try:  # pragma: no cover - optional dependency during tests
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from PySide6.QtCore import QCoreApplication

from hushdesk.pdf.columns import select_audit_columns
from hushdesk.pdf.dates import format_mmddyyyy, resolve_audit_date
from hushdesk.workers.audit_worker import AuditWorker


DEFAULT_COUNTS: Dict[str, int] = {
    "reviewed": 0,
    "held_appropriate": 0,
    "hold_miss": 0,
    "compliant": 0,
    "dcd": 0,
}


@dataclass
class RunCapture:
    """Accumulates signals emitted by ``AuditWorker`` during a headless run."""

    pages: Optional[int] = None
    bands: Optional[int] = None
    counts: Dict[str, int] = field(default_factory=dict)
    txt_path: Optional[Path] = None
    audit_label: Optional[str] = None
    logs: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    scout_lines: List[str] = field(default_factory=list)
    no_data: bool = False

    _PAGES_RE = re.compile(r"pages=(\d+)")
    _BANDS_RE = re.compile(r"Processing (\d+) band pages")

    def attach(self, worker: AuditWorker) -> None:
        worker.log.connect(self._on_log)
        worker.warning.connect(self._on_warning)
        worker.summary_counts.connect(self._on_summary)
        worker.saved.connect(self._on_saved)
        worker.finished.connect(self._on_finished)
        worker.no_data_for_date.connect(self._on_no_data)
        worker.audit_date_text.connect(self._on_audit_label)

    # --- Signal handlers -------------------------------------------------

    def _on_log(self, message: str) -> None:
        text = message.strip()
        if not text:
            return
        self.logs.append(text)
        if text.startswith("SCOUT —"):
            self.scout_lines.append(text)
        if self.pages is None:
            match = self._PAGES_RE.search(text)
            if match:
                try:
                    self.pages = int(match.group(1))
                except ValueError:
                    pass
        if self.bands is None:
            match = self._BANDS_RE.search(text)
            if match:
                try:
                    self.bands = int(match.group(1))
                except ValueError:
                    pass

    def _on_warning(self, message: str) -> None:
        text = message.strip()
        if text:
            self.warnings.append(text)

    def _on_summary(self, counts: Dict[str, int]) -> None:
        self.counts = {key: int(value) for key, value in counts.items()}

    def _on_saved(self, path_str: str) -> None:
        if path_str:
            self.txt_path = Path(path_str)

    def _on_finished(self, path_obj: Path) -> None:
        if path_obj:
            self.txt_path = Path(path_obj)

    def _on_no_data(self) -> None:
        self.no_data = True

    def _on_audit_label(self, label: str) -> None:
        text = label.strip()
        if text:
            self.audit_label = text


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the HushDesk BP audit without GUI.")
    parser.add_argument(
        "--mar",
        required=True,
        help="Path to the MAR PDF to audit.",
    )
    parser.add_argument(
        "--audit",
        help="Explicit audit date (MM/DD/YYYY). Overrides environment/default detection.",
    )
    parser.add_argument(
        "--scout",
        action="store_true",
        help="Emit SCOUT candidate lines regardless of environment configuration.",
    )
    parser.add_argument(
        "--pages",
        help="Comma-separated list of 1-based page numbers to audit.",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Print raw spans and fallback cluster details for each audited band.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def run_headless(
    mar_path: Path,
    *,
    audit: Optional[str] = None,
    scout: bool = False,
    pages: Optional[Iterable[int]] = None,
    trace: bool = False,
) -> Dict[str, object]:
    """Execute the audit pipeline for ``mar_path`` and return a summary dict."""

    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is required for headless runs.")

    if not mar_path.exists():
        raise FileNotFoundError(f"MAR path not found: {mar_path}")

    _ = QCoreApplication.instance() or QCoreApplication([])

    audit_date = _resolve_audit_date(mar_path, audit)
    audit_text = format_mmddyyyy(audit_date)

    initial_scout_env = os.getenv("HUSHDESK_SCOUT")
    effective_scout = scout or initial_scout_env == "1"

    doc_pages, band_count = _inspect_document(mar_path, audit_date)

    page_filter = list(pages) if pages else None
    worker = AuditWorker(mar_path, delay=0.0, page_filter=page_filter, trace=trace)
    capture = RunCapture()
    capture.attach(worker)

    with contextlib.ExitStack() as stack:
        stack.enter_context(_temporary_env("HUSHDESK_AUDIT_DATE_MMDDYYYY", audit_text))
        if effective_scout and initial_scout_env != "1":
            stack.enter_context(_temporary_env("HUSHDESK_SCOUT", "1"))
        worker.run()

    capture.pages = capture.pages or doc_pages
    capture.bands = capture.bands or band_count
    counts = {**DEFAULT_COUNTS, **capture.counts}

    summary = {
        "pages": capture.pages or 0,
        "bands": capture.bands or 0,
        "counts": counts,
        "txt_path": str(capture.txt_path) if capture.txt_path else None,
        "audit_label": capture.audit_label or f"{audit_text} — Central",
        "scout_lines": capture.scout_lines,
        "logs": capture.logs,
        "warnings": capture.warnings,
        "no_data": capture.no_data,
    }

    _print_summary(summary)
    if effective_scout and capture.scout_lines:
        for line in capture.scout_lines[:10]:
            print(line)
    if trace:
        for line in capture.logs:
            if line.startswith("TRACE —"):
                print(line)

    return summary


def _resolve_audit_date(mar_path: Path, override: Optional[str]) -> date:
    if override:
        return _parse_mmddyyyy(override)

    env_value = os.getenv("HUSHDESK_AUDIT_DATE_MMDDYYYY")
    if env_value:
        try:
            return _parse_mmddyyyy(env_value)
        except ValueError:
            print(
                f"WARNING: ignoring invalid HUSHDESK_AUDIT_DATE_MMDDYYYY={env_value!r}",
                file=sys.stderr,
            )

    return resolve_audit_date(mar_path)


def _parse_mmddyyyy(raw_value: str) -> date:
    match = re.fullmatch(r"\s*(\d{2})/(\d{2})/(\d{4})\s*", raw_value)
    if not match:
        raise ValueError(f"Invalid MM/DD/YYYY date: {raw_value!r}")
    month, day, year = (int(group) for group in match.groups())
    return date(year=year, month=month, day=day)


def _inspect_document(mar_path: Path, audit_date: date) -> tuple[int, int]:
    if fitz is None:
        return (0, 0)
    try:
        with fitz.open(mar_path) as doc:
            bands = select_audit_columns(doc, audit_date)
            return (len(doc), len(bands))
    except Exception as exc:  # pragma: no cover - defensive
        print(f"WARNING: unable to inspect MAR ({exc})", file=sys.stderr)
        return (0, 0)


def _parse_page_filter(raw_value: Optional[str]) -> Optional[List[int]]:
    if not raw_value:
        return None
    tokens = [token.strip() for token in re.split(r"[,\s]+", raw_value) if token.strip()]
    if not tokens:
        return None
    pages: set[int] = set()
    for token in tokens:
        try:
            page_num = int(token)
        except ValueError as exc:
            raise ValueError(f"Invalid page index {token!r}") from exc
        if page_num <= 0:
            raise ValueError("Page numbers must be positive integers")
        pages.add(page_num - 1)
    return sorted(pages)


@contextlib.contextmanager
def _temporary_env(key: str, value: str) -> Iterable[None]:
    original = os.environ.get(key)
    os.environ[key] = value
    try:
        yield
    finally:
        if original is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original


def _print_summary(summary: Dict[str, object]) -> None:
    pages = int(summary.get("pages") or 0)
    bands = int(summary.get("bands") or 0)
    counts = summary.get("counts", DEFAULT_COUNTS)
    reviewed = int(counts.get("reviewed", 0))
    held_ok = int(counts.get("held_appropriate", 0))
    hold_miss = int(counts.get("hold_miss", 0))
    compliant = int(counts.get("compliant", 0))
    dcd = int(counts.get("dcd", 0))
    txt_path = summary.get("txt_path") or "N/A"

    print(f"Pages {pages} | Bands {bands}")
    print(
        "Reviewed {r} · Held-OK {h_ok} · Hold-Miss {h_miss} · Compliant {comp} · DC’D {dcd}".format(
            r=reviewed,
            h_ok=held_ok,
            h_miss=hold_miss,
            comp=compliant,
            dcd=dcd,
        )
    )
    print(f"TXT: {txt_path}")


def main(argv: Optional[Iterable[str]] = None) -> int:
    try:
        args = parse_args(argv)
        page_filter = _parse_page_filter(args.pages)
        run_headless(
            Path(args.mar).expanduser().resolve(),
            audit=args.audit,
            scout=args.scout,
            pages=page_filter,
            trace=args.trace,
        )
        return 0
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
