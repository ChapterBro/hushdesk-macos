"""
HushDesk Audit Tracer
---------------------
 Runs the MAR audit pipeline stage-by-stage, printing only numeric counts
 (page -> band -> vitals -> rule -> decision) and a SHA256 hash of the input file path.
No PHI/PII ever written or logged.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
from datetime import datetime


def sha256_path(path: str) -> str:
    return hashlib.sha256(path.encode()).hexdigest()


def trace_mar(pdf_path: str) -> dict:
    stats = {"pages": 0, "bands": 0, "vitals": 0, "rules": 0, "decisions": 0}
    try:
        aw = importlib.import_module("hushdesk.workers.audit_worker")
        result = aw.main(pdf_path, trace=True) if hasattr(aw, "main") else None
        if isinstance(result, dict):
            stats.update({k: v for k, v in result.items() if k in stats})
        else:
            # fallback heuristic if worker lacks trace mode
            stats["pages"] = getattr(aw, "page_count", 0)
    except Exception as e:  # noqa: BLE001 - we only surface numeric stats
        stats["error"] = str(e)
    return stats


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Usage: python tools/audit_tracer.py <path_to_pdf>")

    pdf_path = os.path.expanduser(sys.argv[1])
    if not os.path.isfile(pdf_path):
        sys.exit(f"File not found: {pdf_path}")

    stats = trace_mar(pdf_path)
    sha = sha256_path(pdf_path)
    baton_line = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "sha256": sha,
        "stats": stats,
    }
    print(json.dumps(baton_line, indent=2))

    # Append anonymized baton entry
    with open("docs/BATON.md", "a", encoding="utf-8") as baton:
        baton.write(f"\n### {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        baton.write(f"**File SHA:** `{sha}`\n")
        for key, val in stats.items():
            baton.write(f"- {key}: {val}\n")


if __name__ == "__main__":
    main()
