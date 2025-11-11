"""Measure renderer performance for a MAR PDF."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import time
from pathlib import Path
from typing import List

import fitz  # type: ignore

from hushdesk.ui.preview_renderer import render_document_page

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover - optional dependency
    from PySide6.QtGui import QGuiApplication  # type: ignore
except Exception:  # pragma: no cover
    QGuiApplication = None  # type: ignore

_QAPP: "QGuiApplication | None" = None


def _sha_path(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()


def _sample_indices(pages: int, target_samples: int) -> List[int]:
    if pages <= 0:
        return []
    if target_samples <= 0 or target_samples >= pages:
        return list(range(pages))
    step = max(1, pages // target_samples)
    indices = list(range(0, pages, step))
    return indices[:target_samples]


def _write_csv_row(
    doc_sha: str,
    dpi: int,
    pages: int,
    samples: int,
    mean_ms: float,
    total_s: float,
) -> None:
    perf_dir = (
        Path.home() / "Library" / "Application Support" / "HushDesk" / "Perf"
    )
    perf_dir.mkdir(parents=True, exist_ok=True)
    csv_path = perf_dir / "metrics.csv"
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with csv_path.open("a", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                timestamp,
                doc_sha,
                dpi,
                pages,
                samples,
                f"{mean_ms:.3f}",
                f"{total_s:.3f}",
            ]
        )


def _ensure_qapp() -> None:
    global _QAPP
    if QGuiApplication is None:
        return
    if QGuiApplication.instance() is None:
        _QAPP = QGuiApplication([])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", help="Path to the MAR PDF to profile")
    parser.add_argument("--dpi", type=int, default=144, help="Render DPI")
    parser.add_argument(
        "--samples",
        type=int,
        default=12,
        help="Number of pages to time (spread across the document)",
    )
    args = parser.parse_args()

    _ensure_qapp()
    pdf_path = Path(args.pdf).expanduser().resolve()
    doc_sha = _sha_path(pdf_path)
    with fitz.open(str(pdf_path)) as doc:  # type: ignore[attr-defined]
        total_pages = len(doc)
        indices = _sample_indices(total_pages, args.samples)
        timings: List[float] = []
        t0 = time.perf_counter()
        for index in indices:
            start = time.perf_counter()
            try:
                render_document_page(
                    doc,
                    index,
                    target_dpi=args.dpi,
                    cache_hint=pdf_path,
                )
                elapsed = (time.perf_counter() - start) * 1000.0
                timings.append(elapsed)
            except Exception:
                timings.append(-1.0)
        total_elapsed = time.perf_counter() - t0

    successes = [value for value in timings if value >= 0.0]
    mean_ms = statistics.fmean(successes) if successes else -1.0
    median_ms = statistics.median(successes) if successes else -1.0
    result = {
        "pdf_sha": doc_sha,
        "dpi": args.dpi,
        "pages": total_pages,
        "samples": len(indices),
        "per_page_ms": timings,
        "mean_ms": mean_ms,
        "median_ms": median_ms,
        "total_s": total_elapsed,
    }
    _write_csv_row(doc_sha, args.dpi, total_pages, len(indices), mean_ms, total_elapsed)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
