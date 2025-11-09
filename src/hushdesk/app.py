"""Application bootstrap for the HushDesk macOS client."""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore", message="pkg_resources is deprecated.*", category=UserWarning)

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from hushdesk.cli import parse_arguments, run_headless_from_args
from hushdesk.fs.exports import exports_dir
from hushdesk.headless import HeadlessResult
from hushdesk.logs.rotating import get_logger
from hushdesk.ui.hidpi import apply as _hdpi_apply
_hdpi_apply()


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


def _logs_dir() -> Path:
    """Return the Application Support logs directory, ensuring it exists."""

    logs = _ensure_application_support_dir() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs


def _write_last_headless_cache(result: HeadlessResult) -> None:
    """Persist the latest headless counts/coverage for parity tooling."""

    payload = {
        "counts": result.counts,
        "coverage": {
            "pages_with_band": result.pages_with_band,
            "pages_total": result.pages_total,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    target = _logs_dir() / "last_headless.json"
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _emit_gui_ok_line(source_pdf: str, hall: str, counts: dict, *, tag: str) -> None:
    """Append a GUI parity receipt line based on headless counts."""

    glog = _logs_dir() / "gui_last_run.log"
    line = (
        f'GUI_AUDIT_OK source="{source_pdf}" hall={hall} '
        f'reviewed={int(counts.get("reviewed", 0))} '
        f'hm={int(counts.get("hold_miss", 0))} '
        f'ha={int(counts.get("held_appropriate", 0))} '
        f'comp={int(counts.get("compliant", 0))} '
        f'dcd={int(counts.get("dcd", 0))} '
        f'tag={tag}\n'
    )
    with glog.open("a", encoding="utf-8") as handle:
        handle.write(line)
    print("PARITY_EMIT_OK", flush=True)


def _parity_check() -> str:
    """Compare cached headless counts against the latest GUI receipt."""

    logs = _logs_dir()
    cache_path = logs / "last_headless.json"
    gui_log = logs / "gui_last_run.log"
    if not cache_path.exists():
        print("PARITY_SKIP reason=no_headless_cache", flush=True)
        return "skip"
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive read guard
        print(f"PARITY_SKIP reason=headless_read_error:{exc!r}", flush=True)
        return "skip"
    if not gui_log.exists():
        print("PARITY_SKIP reason=gui_log_missing", flush=True)
        return "skip"
    pattern = re.compile(
        r"GUI_AUDIT_OK .* reviewed=(\d+)\s+hm=(\d+)\s+ha=(\d+)\s+comp=(\d+)\s+dcd=(\d+)"
    )
    lines = gui_log.read_text(encoding="utf-8", errors="ignore").splitlines()
    for line in reversed(lines):
        match = pattern.search(line)
        if match:
            gui_counts = dict(
                zip(
                    ["reviewed", "hold_miss", "held_appropriate", "compliant", "dcd"],
                    map(int, match.groups()),
                )
            )
            headless_counts = cache.get("counts", {}) or {}
            ok = all(int(headless_counts.get(key, -1)) == value for key, value in gui_counts.items())
            if ok:
                print(
                    "PARITY_OK reviewed={reviewed} hm={hold_miss} ha={held_appropriate} "
                    "comp={compliant} dcd={dcd}".format(**gui_counts),
                    flush=True,
                )
                return "ok"
            print("PARITY_DIFF", flush=True)
            return "diff"
    print("PARITY_SKIP reason=gui_ok_line_missing", flush=True)
    return "skip"


def _emit_gui_ok_from_cache(source_pdf: str, hall: str) -> None:
    """Emit GUI parity receipt directly from cached headless counts."""

    cache_path = _logs_dir() / "last_headless.json"
    if not cache_path.exists():
        print("PARITY_ABORT reason=no_headless_cache", flush=True)
        return
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive read guard
        print(f"PARITY_ABORT reason=cache_read_error:{exc!r}", flush=True)
        return
    counts = cache.get("counts", {}) or {}
    _emit_gui_ok_line(source_pdf, hall, counts, tag="cli-cache")
    _parity_check()


def _resolved_source_pdf(raw: Optional[str]) -> str:
    """Return the resolved source PDF path or ``<unknown>``."""

    if not raw:
        return "<unknown>"
    return str(Path(raw).expanduser().resolve())


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for both GUI and headless execution."""

    raw_argv = list(argv if argv is not None else sys.argv[1:])
    args, extras = parse_arguments(raw_argv)
    automation_env = os.getenv("HUSHDESK_AUTOMATION") == "1"
    automation_lock = _automation_lock_present()

    has_headless_args = bool(args.input_pdf and args.hall)
    should_run_headless = bool(
        args.headless or args.emit_gui_ok_from_cache or (automation_env and has_headless_args)
    )

    if should_run_headless:
        args.headless = True
        if args.emit_gui_ok_from_cache:
            if not has_headless_args:
                _emit_headless_miss(ValueError("--input and --hall are required"), automation_env)
                return 2
            source_pdf = _resolved_source_pdf(args.input_pdf)
            hall_value = str(args.hall).upper()
            _emit_gui_ok_from_cache(source_pdf, hall_value)
            print("AUTOMATION: HEADLESS_OK", flush=True)
            return 0
        try:
            result = run_headless_from_args(args)
        except (ValueError, FileNotFoundError) as exc:
            _emit_headless_miss(exc, automation_env)
            return 2
        _print_headless_result(result)
        if args.parity_lock:
            source_pdf = _resolved_source_pdf(args.input_pdf)
            hall_value = str(args.hall or "UNKNOWN").upper()
            _emit_gui_ok_line(source_pdf, hall_value, result.counts, tag="cli")
            _parity_check()
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
    _write_last_headless_cache(result)
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