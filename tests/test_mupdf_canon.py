from __future__ import annotations

from pathlib import Path

import fitz  # type: ignore

from hushdesk.pdf.mupdf_canon import CanonLine, CanonWord, iter_canon_pages


def _make_rotated_pdf(tmp_path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=200, height=120)
    page.insert_text((20, 30), "Header 1", fontsize=14)
    page.insert_text((20, 60), "42", fontsize=12)
    page.draw_line((10, 80), (180, 80))
    page.draw_line((60, 10), (60, 110))
    page.set_rotation(90)
    pdf_path = tmp_path / "rotated.pdf"
    doc.save(pdf_path)
    doc.close()
    return pdf_path


def test_iter_canon_pages_unrotates(tmp_path: Path) -> None:
    pdf_path = _make_rotated_pdf(tmp_path)

    pages = list(iter_canon_pages(pdf_path))
    assert len(pages) == 1

    page = pages[0]
    assert page.width > page.height  # rotation removed
    assert page.height > 0
    assert all(isinstance(word, CanonWord) for word in page.words)
    assert all(isinstance(line, CanonLine) for line in page.vlines + page.hlines)

    # y-top should always be < y-bottom after canonicalization
    for word in page.words:
        x0, y0, x1, y1 = word.bbox
        assert y0 <= y1
        assert x0 <= x1

    # We drew one horizontal and one vertical line.
    assert any(line.orientation == "h" for line in page.hlines)
    assert any(line.orientation == "v" for line in page.vlines)
