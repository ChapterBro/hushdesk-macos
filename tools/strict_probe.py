from __future__ import annotations

import hashlib
import json
import os
import re

import fitz  # type: ignore


def main() -> None:
    mar = os.environ.get("MAR")
    if not mar or not os.path.exists(mar):
        raise SystemExit("Set MAR to a local PDF path via MAR env var")

    sha = hashlib.sha256(os.path.abspath(mar).encode()).hexdigest()
    doc = fitz.open(mar)

    pat_sbp = re.compile(r"\bSBP\b\s*(?:LESS\s+THAN|GREATER\s+THAN|[<>])\s*\d{2,3}", re.I)
    pat_hr = re.compile(r"\b(?:HR|PULSE)\b\s*(?:LESS\s+THAN|GREATER\s+THAN|[<>])\s*\d{2,3}", re.I)

    hits = []
    for i, page in enumerate(doc):
        txt = page.get_text("text")
        sbp_hits = pat_sbp.findall(txt or "")
        hr_hits = pat_hr.findall(txt or "")
        if sbp_hits or hr_hits:
            hits.append({
                "page": i + 1,
                "sbp": sbp_hits,
                "hr": hr_hits,
            })

    out = {
        "path_sha": sha,
        "pages": len(doc),
        "hits": hits,
        "total_pages_with_hits": len(hits),
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
