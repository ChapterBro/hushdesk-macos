import fitz

from hushdesk.ui.preview_renderer import make_render_matrix


def test_one_inch_square_matches_target_dpi_pixels():
    with fitz.open() as doc:
        page = doc.new_page(width=720, height=360)  # 10" x 5" at 72 pt/in
        target_dpi = 144  # 2x scale
        matrix = make_render_matrix(page, target_dpi=target_dpi, force_landscape=True)
        inch_square = fitz.Rect(0, 0, 72, 72)  # one inch in PDF points
        projected = fitz.Rect(inch_square).transform(matrix)
        assert int(round(projected.width)) == target_dpi
        assert int(round(projected.height)) == target_dpi
