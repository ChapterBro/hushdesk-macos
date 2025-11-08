import fitz
from hushdesk.ui.preview_renderer import make_render_matrix

def _size_after(page, mat):
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return (pix.width, pix.height)

def test_force_landscape_turns_portrait_wide():
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=900)  # portrait
        mat = make_render_matrix(page, target_dpi=72, force_landscape=True)
        w, h = _size_after(page, mat)
        assert w >= h  # enforced landscape


def test_neutralizes_pdf_rotate_flag():
    with fitz.open() as doc:
        page = doc.new_page(width=900, height=600)  # landscape
        page.set_rotation(90)  # embedded /Rotate
        mat = make_render_matrix(page, target_dpi=72, force_landscape=True)
        w, h = _size_after(page, mat)
        assert w >= h
