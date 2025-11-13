## Quick dev bring-up

```bash
# From repo root
python3 -m venv .venv311
source .venv311/bin/activate

# Install dev deps (preferred); falls back to explicit pins in CI only
pip install -r requirements-dev.txt

# Verify imports (no PDFs required)
python3 -m compileall -q src && python3 -m compileall -q tools
PYTHONNOUSERSITE=1 PYTHONPATH="$PWD/src" QT_QPA_PLATFORM=offscreen python3 tools/import_smoke.py
# expect: {"ok": true, "errors": []} and "IMPORT_OK"
```

### Notes

* `Pillow` is required by `src/hushdesk/pdf/qa_overlay.py` (rendering/diagnostics).
* `PyMuPDF` is the PDF engine.
* CI is PDF-free and runs: compile -> import_smoke -> strict-only tests.
