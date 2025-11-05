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

## Headless Run
- Set `HUSHDESK_AUDIT_DATE_MMDDYYYY=MM/DD/YYYY` and `HUSHDESK_SCOUT=1` when needed
- Execute `python -m hushdesk.dev.headless --mar "<path-to-MAR.pdf>"`
- Output is TXT-only for binder-ready review

## Build
- Create app + DMG artifacts: `./scripts/build`

## Sign
- Provide signing identity and team: `CODESIGN_ID="Developer ID Application: <Name> (<TEAM>)" TEAM_ID="<TEAM>" ./scripts/sign`

## Notarize
- Export Apple credentials: `APPLE_ID`, `APP_SPECIFIC_PASSWORD`, and `TEAM_ID`
- Run `./scripts/notarize` to submit, staple, and verify the DMG

## Release
- Publish the notarized DMG: `VERSION=0.1.0 ./scripts/release`
