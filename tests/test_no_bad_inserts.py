from pathlib import Path
import re

BAD_PATTERNS = [
    r"\bself\.self\b",
    r"\bselfself\b",
    r"^\s*\.\s*fitInView\s*\(",  # leading-dot call
    r"from\s+hushdesk\.ui\.preview_renderer\s+import\s*\([^)]*from\s+hushdesk",  # nested import in parens
]

def test_no_bad_inserts_patterns():
    src_root = Path("src")
    offenders = []
    for path in src_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pat in BAD_PATTERNS:
            if re.search(pat, text, flags=re.M):
                offenders.append(f"{path} matched {pat}")
    assert not offenders, "Found bad insert patterns:\n" + "\n".join(offenders)
