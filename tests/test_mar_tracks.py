from __future__ import annotations

from pathlib import Path

import fitz  # type: ignore

from hushdesk.pdf.mar_tracks import detect_tracks_on_page
from hushdesk.pdf.mupdf_canon import iter_canon_pages


def _make_tracks_pdf(tmp_path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=240, height=320)
    # Audit column roughly at x ∈ [120, 160]
    # Track 1 (no BP evidence to ensure optional handling)
    page.insert_text((200, 80), "0800", fontsize=12)
    page.insert_text((135, 90), "120/80", fontsize=11)
    # Track 2 with BP + Pulse
    page.insert_text((200, 160), "6a-10", fontsize=12)
    page.insert_text((198, 146), "BP", fontsize=11)
    page.insert_text((138, 170), "118/74", fontsize=11)
    page.insert_text((198, 210), "Pulse", fontsize=11)
    page.insert_text((138, 212), "60/min", fontsize=11)
    # Track 3 (HS) without pulse
    page.insert_text((200, 240), "HS", fontsize=12)
    page.insert_text((198, 226), "BP", fontsize=11)
    page.insert_text((138, 250), "126/76", fontsize=11)

    pdf_path = tmp_path / "tracks.pdf"
    doc.save(pdf_path)
    doc.close()
    return pdf_path


def test_detect_tracks_on_page(tmp_path: Path) -> None:
    pdf_path = _make_tracks_pdf(tmp_path)
    canon_page = next(iter(iter_canon_pages(pdf_path)))

    band = (120.0, 160.0)
    summary = detect_tracks_on_page(canon_page, band)
    assert summary is not None
    assert len(summary.tracks) == 3
    assert summary.bp_pairs >= 1
    assert any(track.pulse_band is not None for track in summary.tracks)
