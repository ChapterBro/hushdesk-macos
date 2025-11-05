# HushDesk (BP Audit) — macOS

See the product spec in **docs/PRD_BP_Mac_v1.0.md**.

Canonical configs:
- hushdesk/config/rules_master_v1.1.1.json
- hushdesk/config/building_master_mac.json

## Run (dev)
- Ensure Python 3.11 is available.
- Run `./scripts/dev` to bootstrap the venv and launch the shell app.
- Audit Date is resolved from filename (previous day, Central). Phase 3 detects per-page Audit-Date column bands, and the UI surfaces Source/pending date headers with live log output and save toasts.
