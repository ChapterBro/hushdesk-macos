# Changelog

## Phase 3 – Semantic Anchors
- feat(layout): semantic day-header detection + per-page column bands in PDF user-space points.
- feat(ui): bind Source and pending Audit Date headers, add log panel with save toasts.
- feat(worker): started/progress/log/saved/warning signals with column band summaries per page.
- refactor(app): drop deprecated Qt6 HiDPI attributes from bootstrap.

## Phase 2 – Date Logic Clamp Stub
- Resolved filename-first audit dates (Central previous day) and surfaced the formatted header value.
- Stubbed audit column clamp wiring with a yellow “No data for selected date” banner when no data is found.
- Added initial date logic tests and a README note about the audit date behavior.

## Phase 1 – Shell App Scaffold
- Added PySide6 app entrypoint with drag-and-drop MAR picker, progress bar, and summary chips.
- Implemented background worker stub that simulates auditing and writes placeholder TXT output.
- Added dev tooling (`scripts/dev`, `.vscode/launch.json`, and PySide6 requirement) to streamline local runs.
