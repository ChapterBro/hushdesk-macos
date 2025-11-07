# HushDesk (macOS, unsigned) — Local Runbook

## One-time build
. .venv_build/bin/activate
PYINSTALLER_BIN=.venv_build/bin/pyinstaller DESKTOP_ALIAS=0 ./scripts/build

## Headless (no GUI)
HUSHDESK_AUTOMATION=1 ./dist/HushDesk.app/Contents/MacOS/HushDesk --headless \
  --input "/Users/<you>/Downloads/Administration Record Report 2025-11-05.pdf" \
  --hall BRIDGEMAN --qa-png debug/qa_pkg.png

## GUI
- Double-click `HushDesk.app`
- Run Audit → chips should match headless
- “Save TXT” uses a Save Panel; cancel or EPERM → saved to `~/Library/Application Support/HushDesk/Exports` (Open Exports link).

## Known receipts
- Headless prints `AUTOMATION: HEADLESS_OK`, summary counts, and TXT path.
- GUI prints `GUI_AUDIT_OK …` and writes to `…/logs/gui_last_run.log`.
- Manual close → `GUI_CLOSED_OK` and `last_exit.json`.

## Notes
- App is **unsigned**; if Gatekeeper warns on first open, Control-click → Open.
- Do not overwrite `.venv_build` casually; reproducibility matters.
