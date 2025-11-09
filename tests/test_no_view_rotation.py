from pathlib import Path
import re


def test_no_view_level_rotation_calls():
    src_root = Path("src")
    offenders = []
    for path in src_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "preview_renderer.py" in str(path):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"\bgraphics[_\.]?view\s*\.\s*rotate\s*\(", line, re.I):
                offenders.append(f"{path}:{i}: {line.strip()}")
            elif re.search(r"\.setRotation\s*\(", line):
                offenders.append(f"{path}:{i}: {line.strip()}")
    assert not offenders, "View-level rotation detected:\n" + "\n".join(offenders)
