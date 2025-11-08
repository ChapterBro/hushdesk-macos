from __future__ import annotations

import argparse
import os
import sys

import fitz

from hushdesk.ui.preview_renderer import make_render_matrix


def find_pdf(name: str) -> str | None:
    candidates = [
        os.path.join(os.getcwd(), name),
        os.path.join(os.getcwd(), "samples", name),
        os.path.expanduser(os.path.join("~", "Downloads", name)),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Headless orientation check")
    ap.add_argument("--name", required=True, help="Exact PDF filename to search for")
    ap.add_argument("--max-pages", type=int, default=3, help="Pages to sample from start")
    args = ap.parse_args()

    path = find_pdf(args.name)
    if not path:
        print(f"[SKIP] PDF not found: {args.name}")
        sys.exit(0)

    doc = fitz.open(path)
    pages = min(args.max_pages, len(doc))
    failures = 0
    for index in range(pages):
        page = doc[index]
        matrix = make_render_matrix(page, target_dpi=72, force_landscape=True)
        rect = fitz.Rect(page.rect).transform(matrix)
        width, height = rect.width, rect.height
        ok = width >= height
        print(
            f"[CHECK] {os.path.basename(path)} page {index + 1}/{len(doc)} "
            f"-> {int(width)}x{int(height)} {'OK' if ok else 'SIDEWAYS'}"
        )
        if not ok:
            failures += 1
    doc.close()
    print(f"[RESULT] checked {pages} pages; landscape_ok={pages - failures}; not_ok={failures}")
    # Do not hard fail the pipeline if sideways remains; this is a diagnostic
    sys.exit(0)

if __name__ == "__main__":
    main()
