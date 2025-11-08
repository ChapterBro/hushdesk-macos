# HushDesk (BP Audit) — macOS

See the product spec in `docs/PRD_BP_Mac_v1.0.md`.

Canonical configs:
- `hushdesk/config/rules_master_v1.1.1.json`
- `hushdesk/config/building_master_mac.json`

Current version: `0.1.0`

## Quickstart (dev)
- Use Python 3.11 and install tooling: `python -m pip install -r requirements-dev.txt`
- Launch the desktop app: `./scripts/dev`
- Default audit date follows the filename-first previous-day policy (America/Chicago)
- GUI smoke: `HUSHDESK_AUDIT_DATE_MM_DD_YYYY=11/03/2025 ./scripts/dev_gui_smoke` then drag-and-drop your MAR; verify chips match headless counts and the Preview overlay highlights the expected bands.

## Optional Performance (Rust Accelerator)
- Install Rust toolchain: `brew install rustup && rustup-init -y`
- Build the native wheel for local development: `python -m pip install -U pip maturin` then `maturin develop`
- Opt-in at runtime: `export HUSHDESK_USE_RUST=1`
- When the native module is missing or disabled, HushDesk automatically falls back to the pure-Python path.

## Headless Run
- Set `HUSHDESK_AUDIT_DATE_MMDDYYYY=MM/DD/YYYY` and `HUSHDESK_SCOUT=1` when needed
- Execute `python -m hushdesk.dev.headless --mar "<path-to-MAR.pdf>"`
- Output is TXT-only for binder-ready review

## Build
- Create app + DMG artifacts: `./scripts/build`
- Stamp overrides: `VERSION=1.2.3 BUILD=20250101120000 ./scripts/build` runs the bundled `scripts/stamp_version` to update `CFBundleShortVersionString`/`CFBundleVersion` inside the packaged app without launching the GUI. The stamping step falls back to `src/hushdesk/__init__.py:__version__` and an auto-generated UTC build number when overrides are not provided.

## For my machine only (unsigned)
1. `./scripts/build`
2. `xattr -dr com.apple.quarantine dist/HushDesk.app`
3. `./Open\ HushDesk.command`

Double-clicking the `.command` opens the app without signing.

## Sign
- Provide signing identity and team: `CODESIGN_ID="Developer ID Application: <Name> (<TEAM>)" TEAM_ID="<TEAM>" ./scripts/sign`

## Notarize
- Export Apple credentials: `APPLE_ID`, `APP_SPECIFIC_PASSWORD`, and `TEAM_ID`
- Run `./scripts/notarize` to submit, staple, and verify the DMG

## Release
- Publish the notarized DMG: `VERSION=0.1.0 ./scripts/release`
<!-- DEV_SETUP:BEGIN -->
## Development Setup (macOS, Python 3.11)

**Requirements**
- Python **3.11** (Homebrew: `brew install python@3.11`)
- `pip`, `venv`
- Dev dependencies pinned in `requirements-dev.txt`:
  - `pymupdf==1.24.10`
  - `Pillow==10.4.0`
  - `pytest==8.3.4`

**Quickstart (Clean Room)**
```bash
# Create and activate a clean venv (Apple Silicon path shown; adjust if Intel)
/opt/homebrew/bin/python3.11 -m venv .venv311  # or $(brew --prefix)/bin/python3.11
source .venv311/bin/activate
export PYTHONNOUSERSITE=1
pip install -U pip wheel setuptools
pip install -r requirements-dev.txt

# Make the src tree importable (until packaging is added)
export PYTHONPATH="$PWD/src"

# Optional: force the audit date during development (MM/DD/YYYY)
export HUSHDESK_AUDIT_DATE_MMDDYYYY=11/06/2025
```

**Smoke Test**

```bash
python -m pytest tests/test_smoke_import.py -v
```

**Manual Import Check**

```bash
python - <<'PYI'
import importlib
for m in ["hushdesk.pdf.dates", "hushdesk.scout.scan", "hushdesk.workers.audit_worker", "fitz"]:
    mod = importlib.import_module(m)
    print(f"[OK] {m} -> {getattr(mod, '__file__', '<builtin>')}")
PYI
```

**Troubleshooting**

* `TypeError` referencing `dataclass(slots=True)`: not using Python 3.11.
* `ModuleNotFoundError: fitz`: install dev requirements to pull in PyMuPDF.
* `ImportError` for `hushdesk.*`: ensure `export PYTHONPATH=src`.

**Next (optional)**

* Replace `PYTHONPATH=src` with proper packaging (`pyproject.toml`) and `pip install -e .`.
<!-- DEV_SETUP:END -->
