# Dev Notes (quick bring-up)

## Verify (no PDFs required)
```bash
python -m venv .venv311 && source .venv311/bin/activate
pip install -r requirements-dev.txt
python -m compileall -q src && python -m compileall -q tools
PYTHONNOUSERSITE=1 PYTHONPATH=src python tools/import_smoke.py   # expect: IMPORT_OK
```

## Strict-only parser policy

Accept only <, >, "less than", "greater than", LT, GT. Ignore =, >=/<=, and "equal/above/below/over/under".

## Baton policy

Log only SHA-256 of file paths; never raw paths or names.
