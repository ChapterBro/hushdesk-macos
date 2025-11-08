from __future__ import annotations

from datetime import date
from pathlib import Path

import fitz  # type: ignore

from hushdesk.pdf.mar_header import (
    audit_date_from_filename,
    band_for_date,
    detect_header,
    find_day_tokens,
    parse_filename_date,
)
from hushdesk.pdf.mupdf_canon import iter_canon_pages


def _make_mar_header_pdf(tmp_path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=240, height=300)
    page.insert_text((40, 40), "November", fontsize=18)
    page.insert_text((80, 60), "4", fontsize=16)
    page.insert_text((140, 60), "5", fontsize=16)
    page.insert_text((200, 60), "6", fontsize=16)
    page.draw_line((60, 10), (60, 280))
    page.draw_line((120, 10), (120, 280))
    page.draw_line((180, 10), (180, 280))
    pdf_path = tmp_path / "Administration Record Report 2025-11-05.pdf"
    doc.save(pdf_path)
    doc.close()
    return pdf_path


def test_header_bands_and_audit_date(tmp_path: Path) -> None:
    pdf_path = _make_mar_header_pdf(tmp_path)
    canon_page = next(iter(iter_canon_pages(pdf_path)))
    tokens = find_day_tokens(canon_page)
    assert [token["text_int"] for token in tokens] == [4, 5, 6]

    detection = detect_header(canon_page)
    assert 4 in detection.day_bands
    x0, x1 = detection.day_bands[5]
    assert x0 < x1

    source_date = parse_filename_date(pdf_path)
    assert source_date == date(2025, 11, 5)
    audit_dt, display = audit_date_from_filename(pdf_path)
    assert audit_dt.date() == date(2025, 11, 4)
    assert audit_dt.tzinfo is not None
    assert display == "11/04/2025"

    band = band_for_date(canon_page, audit_dt)
    assert band is not None
    bx0, bx1 = band
    assert bx0 < bx1
