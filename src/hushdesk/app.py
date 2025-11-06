"""Application bootstrap for the HushDesk macOS client."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from hushdesk.cli import parse_arguments, run_headless_from_args
from hushdesk.fs.exports import exports_dir
from hushdesk.headless import HeadlessResult
from hushdesk.logs.rotating import get_logger


def _ensure_application_support_dir() -> Path:
    """Ensure the Application Support directory exists and return its path."""
    app_support = Path.home() / "Library" / "Application Support" / "HushDesk"
    app_support.mkdir(parents=True, exist_ok=True)
    return app_support


def _automation_lock_present() -> bool:
    """Return ``True`` when an automation lock file is present."""

    runtime_base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    candidates = {
        Path.cwd() / "automation.lock",
        runtime_base / "automation.lock",
        Path.home() / "Library" / "Application Support" / "HushDesk" / "automation.lock",
    }
    return any(path.exists() for path in candidates)


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for both GUI and headless execution."""

    raw_argv = list(argv if argv is not None else sys.argv[1:])
    args, extras = parse_arguments(raw_argv)
    automation_env = os.getenv("HUSHDESK_AUTOMATION") == "1"
    automation_lock = _automation_lock_present()

    has_headless_args = bool(args.input_pdf and args.hall)
    should_run_headless = bool(args.headless or (automation_env and has_headless_args))

    if should_run_headless:
        args.headless = True
        try:
            result = run_headless_from_args(args)
        except (ValueError, FileNotFoundError) as exc:
            _emit_headless_miss(exc, automation_env)
            return 2
        _print_headless_result(result)
        return result.exit_code

    if automation_env or automation_lock:
        print("GUI_SUPPRESSED automation", flush=True)
        return 0

    sys.argv = [sys.argv[0]] + extras
    return _launch_gui()


def _launch_gui() -> int:
    from PySide6.QtWidgets import QApplication

    from hushdesk.ui.main_window import MainWindow

    print("HushDesk: launching GUI", flush=True)
    runtime_base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    print(f"HushDesk: runtime base {runtime_base}", flush=True)
    print(f"HushDesk: executable {Path(sys.executable).resolve()}", flush=True)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("HushDesk")
    app.setOrganizationName("HushDesk")

    app_support_dir = _ensure_application_support_dir()
    _ = get_logger()
    print(f"HushDesk: using support dir {app_support_dir}", flush=True)
    export_dir = exports_dir()
    print(f"HushDesk: exports dir {export_dir}", flush=True)
    window = MainWindow(app_support_dir=app_support_dir)
    window.show()
    print("HushDesk: main window shown", flush=True)

    def _handle_manual_close() -> None:
        payload = {
            "reason": "manual_close",
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        target = app_support_dir / "last_exit.json"
        try:
            target.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass
        print("GUI_CLOSED_OK", flush=True)

    app.aboutToQuit.connect(_handle_manual_close)

    result = app.exec()
    print(f"HushDesk: event loop exited ({result})", flush=True)
    return result


def _print_headless_result(result: HeadlessResult) -> None:
    print(result.summary_line, flush=True)
    coverage_line = f"COVERAGE page_bands={result.pages_with_band}/{result.pages_total}"
    print(coverage_line, flush=True)
    if result.txt_path:
        print(f"TXT: {result.txt_path}", flush=True)
    else:
        print("TXT: <missing>", flush=True)
    print("AUTOMATION: HEADLESS_OK", flush=True)
    app_support = Path.home() / "Library" / "Application Support" / "HushDesk" / "logs"
    app_support.mkdir(parents=True, exist_ok=True)
    payload = {
        "counts": result.counts,
        "coverage": {
            "pages_with_band": result.pages_with_band,
            "pages_total": result.pages_total,
        },
    }
    (app_support / "last_headless.json").write_text(json.dumps(payload, indent=2))
    print("HEADLESS_COUNTS_SAVED", flush=True)
    for warning in result.warnings:
        print(f"Warning: {warning}", file=sys.stderr, flush=True)


def _emit_headless_miss(exc: Exception, automation: bool) -> None:
    label = "AUTOMATION_MISS" if automation else "HEADLESS_MISS"
    if isinstance(exc, FileNotFoundError):
        reason = "input_missing"
    else:
        reason = "invalid_args"
    print(f"{label} reason={reason}", flush=True)
    print(f"Headless error: {exc}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    sys.exit(main())
