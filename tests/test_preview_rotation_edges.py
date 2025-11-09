import fitz

from hushdesk.ui.preview_renderer import make_render_matrix


def _width_height(page, mat):
    rect = fitz.Rect(page.rect).transform(mat)
    return rect.width, rect.height


def test_rotate_270_portrait_enforced_landscape():
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=900)  # portrait box
        page.set_rotation(270)  # embedded /Rotate flag
        mat = make_render_matrix(page, target_dpi=72, force_landscape=True)
        w, h = _width_height(page, mat)
        assert w >= h  # final orientation stays landscape


def test_rotate_180_landscape_stays_landscape():
    with fitz.open() as doc:
        page = doc.new_page(width=900, height=600)  # landscape box
        page.set_rotation(180)
        mat = make_render_matrix(page, target_dpi=72, force_landscape=True)
        w, h = _width_height(page, mat)
        assert w >= h  # still landscape despite 180 deg metadata


def test_rotate_0_portrait_enforced_landscape():
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=900)  # portrait box
        mat = make_render_matrix(page, target_dpi=72, force_landscape=True)
        w, h = _width_height(page, mat)
        assert w >= h
