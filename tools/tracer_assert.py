"""Lightweight guardrails for the MAR tracer output."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path


def _last_json_line(stream: str):
    """Return the final line that parses as JSON, if any."""

    for line in reversed([chunk.strip() for chunk in stream.splitlines() if chunk.strip()]):
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def _run_tracer(pdf_path: Path) -> tuple[subprocess.CompletedProcess[str], dict | None]:
    cmd = f"{shlex.quote(sys.executable)} tools/audit_tracer.py {shlex.quote(str(pdf_path))}"
    proc = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    payload = _last_json_line(proc.stdout)
    return proc, payload


def _baseline_parsed_from_file(path: Path | None) -> int | None:
    if not path:
        return None
    try:
        text = path.expanduser().read_text(encoding="utf-8")
    except OSError:
        return None
    payload = _last_json_line(text) if text else None
    if not payload:
        return None
    try:
        breakdown = payload.get("rules_source_breakdown") or {}
        return int(breakdown.get("parsed", 0))
    except (ValueError, TypeError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", help="Path to local MAR (NEVER committed)")
    parser.add_argument("--min-bands", type=int, default=112)
    parser.add_argument(
        "--use-pages-as-min-bands",
        action="store_true",
        default=False,
        help="Require bands to meet counts.pages when available (otherwise uses --min-bands)",
    )
    parser.add_argument("--max-gated-ratio", type=float, default=0.15, help="gated/vitals ceiling")
    parser.add_argument(
        "--min-parsed",
        type=int,
        default=0,
        help="floor for rules_source_breakdown.parsed (0 disables the check)",
    )
    parser.add_argument(
        "--baseline-parsed",
        type=int,
        default=None,
        help="Require parsed count to strictly exceed this baseline value",
    )
    parser.add_argument(
        "--baseline-json",
        type=Path,
        default=None,
        help="Optional path to saved tracer JSON (last line parsed for baseline).",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser()
    proc, payload = _run_tracer(pdf_path)

    if not payload:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "no-json",
                    "stdout_tail": proc.stdout[-400:],
                    "stderr_tail": proc.stderr[-400:],
                }
            )
        )
        sys.exit(2)

    counts = payload.get("counts", {})
    bands = int(counts.get("bands", 0))
    pages = int(counts.get("pages", 0))
    vitals = int(counts.get("vitals", 0))
    gated = payload.get("gated", {})
    gated_total = int(gated.get("sbp", 0)) + int(gated.get("hr", 0))
    ratio = (gated_total / vitals) if vitals > 0 else 0.0
    parsed = int((payload.get("rules_source_breakdown") or {}).get("parsed", 0))

    ok = True
    reasons: list[str] = []
    min_bands = args.min_bands
    if args.use_pages_as_min_bands and pages > 0:
        min_bands = pages

    if bands < min_bands:
        ok = False
        reasons.append(f"bands<{min_bands} (got {bands})")
    if vitals > 0 and ratio > args.max_gated_ratio:
        ok = False
        reasons.append(f"gated_ratio>{args.max_gated_ratio:.2f} (got {ratio:.3f})")
    if args.min_parsed and parsed < args.min_parsed:
        ok = False
        reasons.append(f"parsed<{args.min_parsed} (got {parsed})")
    baseline_parsed = args.baseline_parsed
    file_baseline = _baseline_parsed_from_file(args.baseline_json)
    if file_baseline is not None:
        baseline_parsed = file_baseline
    if baseline_parsed is not None and parsed <= baseline_parsed:
        ok = False
        reasons.append(
            f"parsed<=baseline ({parsed} <= {baseline_parsed})"
        )

    result = {
        "ok": ok,
        "bands": bands,
        "pages": pages,
        "vitals": vitals,
        "gated_total": gated_total,
        "gated_ratio": round(ratio, 3),
        "min_bands": min_bands,
        "parsed": parsed,
        "baseline_parsed": baseline_parsed,
        "reasons": reasons,
    }
    print(json.dumps(result))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
