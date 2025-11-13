**Housekeeping PR — guardrails & audit (no phase code)**

**Branch:** `chore/housekeeping-20251112T060658Z` @ `47db714`  
**Compare:** https://github.com/ChapterBro/hushdesk-macos/compare/main...chore/housekeeping-20251112T060658Z?expand=1

### Includes
- `.github/AUDIT_BRANCHES.md`, `.github/AUDIT_PLAN.tsv`
- `.githooks/pre-commit` (block PDFs/Office & raw paths in `docs/BATON.md`)
- `.github/workflows/ci.yml` (compile src/tools + import-smoke + strict-only tests)
- `.gitignore`, `docs/DEV_NOTES.md`

### Excludes
- **No phase code changes**
- **No PDFs or names** in repo/baton

### Diff summary vs main
```
 .githooks/pre-commit                 |  13 ++
 .github/AUDIT_BRANCHES.md            |   8 +
 .github/AUDIT_PLAN.tsv               |   5 +
 .github/HOUSEKEEPING_PR.md           |  44 +++++
 .github/workflows/ci.yml             |  30 ++++
 .gitignore                           |  11 ++
 docs/BATON.md                        |  93 +++++++++++
 docs/DEV_NOTES.md                    |  17 ++
 src/hushdesk/engine/audit.py         | 110 ++++++++++++
 src/hushdesk/pdf/band_resolver.py    | 152 +++++++++++++++++
 src/hushdesk/pdf/dates.py            |  12 ++
 src/hushdesk/pdf/mar_grid_extract.py |  90 +++++++---
 src/hushdesk/pdf/mar_parser_mupdf.py |  16 +-
 src/hushdesk/pdf/mar_tokens.py       | 315 +++++++++++++++++++++++++++++++++++
 src/hushdesk/pdf/spatial_index.py    |  46 +++++
 src/hushdesk/pdf/time_slots.py       | 132 +++++++++++++++
 src/hushdesk/pdf/vitals_bounds.py    |  37 ++++
 src/hushdesk/report/model.py         |   4 +-
 src/hushdesk/scout/__init__.py       |   5 +
 src/hushdesk/scout/scan.py           |  26 +++
 tests/test_band_resolver_fuzz.py     |  40 +++++
 tests/test_label_proximity_fuzz.py   |  48 ++++++
 tools/audit_tracer.py                |  26 +++
 tools/import_smoke.py                |  68 ++++++++
 tools/tracer_assert.py               |   3 +
 25 files changed, 1323 insertions(+), 28 deletions(-)
```

### Changed files
```
.githooks/pre-commit
.github/AUDIT_BRANCHES.md
.github/AUDIT_PLAN.tsv
.github/HOUSEKEEPING_PR.md
.github/workflows/ci.yml
.gitignore
docs/BATON.md
docs/DEV_NOTES.md
src/hushdesk/engine/audit.py
src/hushdesk/pdf/band_resolver.py
src/hushdesk/pdf/dates.py
src/hushdesk/pdf/mar_grid_extract.py
src/hushdesk/pdf/mar_parser_mupdf.py
src/hushdesk/pdf/mar_tokens.py
src/hushdesk/pdf/spatial_index.py
src/hushdesk/pdf/time_slots.py
src/hushdesk/pdf/vitals_bounds.py
src/hushdesk/report/model.py
src/hushdesk/scout/__init__.py
src/hushdesk/scout/scan.py
tests/test_band_resolver_fuzz.py
tests/test_label_proximity_fuzz.py
tools/audit_tracer.py
tools/import_smoke.py
tools/tracer_assert.py
```

> After merge: protect `main` (require CI + review), then proceed to Phase 6 from a clean baseline.
