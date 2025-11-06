from hushdesk.pdf.mar_parser_mupdf import _CoverageProbe


def test_coverage_counts_present():
    probe = _CoverageProbe(total=3, with_band=2)
    pages_total, pages_with_band = probe()
    assert pages_total == 3
    assert pages_with_band == 2
