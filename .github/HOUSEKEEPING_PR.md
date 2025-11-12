**Housekeeping PR — guardrails & audit (no phase code)**

**Branch:** `chore/housekeeping-20251112T060658Z` @ `1f22c20`  
**Compare:** https://github.com/ChapterBro/hushdesk-macos/compare/main...chore/housekeeping-20251112T060658Z?expand=1

### Includes
- `.github/AUDIT_BRANCHES.md`, `.github/AUDIT_PLAN.tsv`
- `.githooks/pre-commit` (PDF/Office blocker + baton guard)
- `.github/workflows/ci.yml` (compile src/tools, import-smoke, strict-only tests)
- `.gitignore`, `docs/DEV_NOTES.md`
- Branch-agnostic `tools/import_smoke.py`

### Excludes
- **No phase code changes**
- **No PDFs or names** anywhere in repo/baton

### Diff summary vs main
```
 .githooks/pre-commit      | 13 +++++++
 .github/AUDIT_BRANCHES.md |  8 ++++
 .github/AUDIT_PLAN.tsv    |  5 +++
 .github/workflows/ci.yml  | 30 +++++++++++++++
 .gitignore                | 11 ++++++
 docs/BATON.md             | 93 +++++++++++++++++++++++++++++++++++++++++++++++
 docs/DEV_NOTES.md         | 17 +++++++++
 tools/import_smoke.py     | 68 ++++++++++++++++++++++++++++++++++
 tools/tracer_assert.py    |  3 ++
 9 files changed, 248 insertions(+)
```

### Changed files
```
.githooks/pre-commit
.github/AUDIT_BRANCHES.md
.github/AUDIT_PLAN.tsv
.github/workflows/ci.yml
.gitignore
docs/BATON.md
docs/DEV_NOTES.md
tools/import_smoke.py
tools/tracer_assert.py
```

> After merge: protect `main` (CI + review, no force-push) and continue Phase 6 on the clean baseline.
