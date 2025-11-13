"""Branch-agnostic import smoke for CI.

The housekeeping branch must remain phase-neutral.  Some helper modules only
exist on the active Phase branches, so we treat them as optional and skip them
when the files are absent.  Core modules still fail fast if imports break.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

SRC_DIR = Path("src")

# Always required for guardrails to be useful across phases.
MANDATORY = [
    "hushdesk.pdf.rules_master",
    "hushdesk.pdf.rules_normalize",
    "hushdesk.pdf.mar_grid_extract",
]

# Helper modules that may not exist on every branch. We only attempt to import
# them when the corresponding source file is present.
OPTIONAL = [
    ("hushdesk.pdf.band_resolver", SRC_DIR / "hushdesk" / "pdf" / "band_resolver.py"),
    ("hushdesk.pdf.spatial_index", SRC_DIR / "hushdesk" / "pdf" / "spatial_index.py"),
    ("hushdesk.pdf.vitals_bounds", SRC_DIR / "hushdesk" / "pdf" / "vitals_bounds.py"),
]

errors: list[dict[str, str]] = []

def record_failure(kind: str, module: str, exc: Exception) -> None:
    errors.append(
        {
            "type": kind,
            "module": module,
            "error": repr(exc),
        }
    )


for module in MANDATORY:
    try:
        importlib.import_module(module)
    except Exception as exc:  # pragma: no cover - only run in CI smoke
        record_failure("mandatory", module, exc)

for module, path in OPTIONAL:
    if not path.exists():
        print(f"SKIP: {module} (missing file: {path})")
        continue
    try:
        importlib.import_module(module)
    except Exception as exc:  # pragma: no cover
        record_failure("optional", module, exc)

result = {"ok": not errors, "errors": errors}
print(json.dumps(result))

if errors and any(err["type"] == "mandatory" for err in errors):
    sys.exit(1)

if errors:
    print("WARN: optional import errors detected; continuing", file=sys.stderr)

print("IMPORT_OK")
sys.exit(0)
