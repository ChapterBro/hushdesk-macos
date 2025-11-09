from pathlib import Path
import re

def test_no_direct_get_pixmap_matrix_calls():
    offenders = []
    for path in Path("src").rglob("*.py"):
        if path.name == "preview_renderer.py":
            continue
        txt = path.read_text(encoding="utf-8", errors="ignore")
        # Flag any page.get_pixmap(matrix=fitz.Matrix(...))
        if re.search(r"\bget_pixmap\s*\(\s*matrix\s*=\s*fitz\.Matrix", txt):
            offenders.append(str(path))
    assert not offenders, "Direct get_pixmap(Matrix) detected (use preview_renderer):\n" + "\n".join(offenders)
