# Changelog

## Unreleased
- accel: fix center dedup, maturin develop OK; parity with Python confirmed.
- preview: overlay dialog with audit column, slot, and glyph highlights plus Results preview launchers.
- ui: QA mode toolbar toggle surfaces inline source/dy diagnostics and slot/vital flags.
- build: packaging metadata tightened, optional release helper, and GUI smoke launcher script.

## Phase 8 – Optional Accelerators
- feat(accel): optional pyo3 crate with Python fallbacks for y-cluster, BP stitch, and band selection wiring in vitals/layout.
- test(accel): parity coverage for accelerators and Rust toggle smoke on audit worker fixtures.
- docs: optional Rust accelerator setup with fallback reminder in README.

## Phase 7 – End-User Trust UI
- feat(ui): Review Explorer panel with grouped decisions, search, and exception filters.
- feat(ui): Evidence drawer shows rule context with PDF previews and per-slot source flags.
- feat(ui): QA Mode toggle with anomaly explorer and slot metrics chips.

## Phase 6 – Release Tooling
- chore(build): add macOS build/sign/notarize/release scripts and set package `__version__`.
- docs(readme): document Quickstart, headless run, build/sign/notarize/release workflow.

## Phase 4 – Vitals & Due-Cell Precedence
- feat(rows): semantic row-band detection for BP/HR and AM/PM lanes inside each med block.
- feat(vitals): BP/HR token parsers with same-column extraction helpers.
- feat(due): due-mark detection with precedence for DC'D, allowed codes, and given entries.
- feat(engine): decision logic wired into the worker to emit HELD-OK / HOLD-MISS / COMPLIANT / DC'D summaries and chip counters.
- test(decide|vitals|due|rows): unit coverage for rule triggers, vitals parsing, due marks, and row-band heuristics.
- fix(worker): ensure no-data signal still fires when column bands are unavailable.
- fix(worker): RuleSpec now uses the `kind` keyword, with an adapter for legacy `rule_kind` usage and dedicated unit tests.
- chore(geometry): add `normalize_rect` helper to ensure PDF rectangles obey x/y ordering.
- fix(rows): normalized label detection, regex-tolerant anchors, and midpoint row-band construction with minimum height fallback.
- fix(vitals|due): clip rectangles use normalized coordinates to avoid empty gathers.
- test(rows|geometry): regression cases for inverted spans, block bounds, and row-band coverage.
- fix(worker): decision loop consumes normalized row bands, counts reviewed per due-cell, and covers Held-OK code + trigger smoke test.
- chore: remove temporary debug logging from rule parsing to keep logs concise.
- fix(rows): accept BP/HR/AM/PM labels anywhere inside the block and extend rule bbox horizontally for vitals zones.
- fix(worker): fallback to whole-block slot when AM/PM rows are absent and sample vitals/due marks with the extended x-span; smoke test updated.

## Phase 3 – Semantic Anchors
- feat(layout): semantic day-header detection + per-page column bands in PDF user-space points.
- feat(ui): bind Source and pending Audit Date headers, add log panel with save toasts.
- feat(worker): started/progress/log/saved/warning signals with column band summaries per page.
- fix(progress): progress bar + Reviewed chip track detected band pages with worker summary counts.
- fix(columns): dedupe header centers, enforce minimum width, and add band-quality regression tests.
- fix(ui): improve dark-theme header contrast and pending label styling.
- refactor(logging): saved output messaging relies solely on the saved signal.
- refactor(app): drop deprecated Qt6 HiDPI attributes from bootstrap.

## Phase 2 – Date Logic Clamp Stub
- Resolved filename-first audit dates (Central previous day) and surfaced the formatted header value.
- Stubbed audit column clamp wiring with a yellow “No data for selected date” banner when no data is found.
- Added initial date logic tests and a README note about the audit date behavior.

## Phase 1 – Shell App Scaffold
- Added PySide6 app entrypoint with drag-and-drop MAR picker, progress bar, and summary chips.
- Implemented background worker stub that simulates auditing and writes placeholder TXT output.
- Added dev tooling (`scripts/dev`, `.vscode/launch.json`, and PySide6 requirement) to streamline local runs.
