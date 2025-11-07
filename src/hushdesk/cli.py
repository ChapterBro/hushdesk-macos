"""Command-line parsing for the HushDesk application."""

from __future__ import annotations

import argparse
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Tuple

from hushdesk.headless import HeadlessOptions, HeadlessResult, execute_headless

HALL_CHOICES = ("MERCER", "HOLADAY", "BRIDGEMAN", "MORTON")


def parse_arguments(argv: Optional[List[str]] = None) -> Tuple[argparse.Namespace, List[str]]:
    """Parse known CLI arguments and return ``(args, extras)``."""

    parser = argparse.ArgumentParser(description="HushDesk blood-pressure audit tool")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the audit pipeline without launching the GUI.",
    )
    parser.add_argument(
        "--input",
        dest="input_pdf",
        help="Absolute or relative path to the MAR PDF.",
    )
    parser.add_argument(
        "--hall",
        choices=HALL_CHOICES,
        help="Target hall for the audit (required in headless mode).",
    )
    parser.add_argument(
        "--date",
        dest="audit_date",
        help="Override audit date in YYYY-MM-DD format (headless mode).",
    )
    parser.add_argument(
        "--qa-png",
        dest="qa_png",
        help="Path to emit QA layout PNG (headless mode).",
    )
    parser.add_argument(
        "--parity-lock",
        action="store_true",
        help="Run headless audit, emit GUI parity receipt, then parity-check counts.",
    )
    parser.add_argument(
        "--emit-gui-ok-from-cache",
        action="store_true",
        help="Emit GUI parity receipt directly from cached headless counts (no audit).",
    )
    parser.add_argument(
        "--log-dir",
        dest="log_dir",
        default="debug",
        help="Directory for structured headless logs (default: debug).",
    )
    parser.add_argument(
        "--log-file",
        dest="log_file",
        help="Optional explicit log file path for headless runs.",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Enable verbose fallback tracing (headless mode).",
    )

    args, extras = parser.parse_known_args(argv)
    return args, extras


def create_headless_options(args: argparse.Namespace) -> HeadlessOptions:
    """Return ``HeadlessOptions`` derived from parsed ``args``."""

    if not args.headless:
        raise ValueError("create_headless_options called without --headless flag")

    if not args.input_pdf:
        raise ValueError("--input is required when --headless is specified")

    if not args.hall:
        raise ValueError("--hall is required when --headless is specified")

    input_path = Path(args.input_pdf).expanduser().resolve()
    hall_value = str(args.hall).upper()

    audit_date = _parse_date(args.audit_date) if args.audit_date else None
    qa_png = str(Path(args.qa_png).expanduser()) if args.qa_png else None
    log_dir = Path(args.log_dir).expanduser()
    log_file = Path(args.log_file).expanduser() if args.log_file else None

    return HeadlessOptions(
        input_pdf=input_path,
        hall=hall_value,
        audit_date=audit_date,
        qa_png=qa_png,
        log_dir=log_dir,
        log_file=log_file,
        trace=bool(args.trace),
    )


def run_headless_from_args(args: argparse.Namespace) -> HeadlessResult:
    """Execute the headless audit using ``args`` and return the result."""

    options = create_headless_options(args)
    return execute_headless(options)


def _parse_date(raw: str) -> date:
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except ValueError as exc:  # pragma: no cover - user input guard
        raise ValueError("--date must be in YYYY-MM-DD format") from exc


__all__ = [
    "parse_arguments",
    "create_headless_options",
    "run_headless_from_args",
    "HALL_CHOICES",
]
