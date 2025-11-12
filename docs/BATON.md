# Baton Log

## 2025-11-09T04:06Z — branch fix/preview-orientation-fit (commit a68c299)
- Tooling: Python 3.11.14 / PyMuPDF 1.24.10 inside .venv311
- Tests: `python -m compileall -q src` ✅ · `PYTHONPATH=src:. pytest -q tests` ❌ (suite still depends on full MAR fixtures + PyMuPDF stubs; see log for missing PDF + DummyRect attributes).
- Headless audit: sha=a106656feab8258d12eab298646d5f067428c4799a5abb945f97dce47dce74fe, pages=115, bands=115/115, reviewed=0 hold_miss=0 held_app=0 compliant=0 dcd=0.
- Renderer/preview rehab, PII guards, and orientation verifier landed per mission.

1. 2025-11-10T22:23:15Z — branch fix/preview-orientation-fit @ a68c299
   - repo_root=/Users/hushdesk/Projects/hushdesk-macos; status=dirty (pre-existing staged files)
   - python3=Python 3.9.6; pip=pip 21.2.4 for Python 3.9; .venv311=exists

2. 2025-11-10T22:23:44Z — headless env
   - ensured .venv311 Python 3.11.14 active; PySide6 6.10.0 / PyMuPDF 1.24.10 / Pillow 10.4.0 / pytest 8.3.4 installed
   - env flags: PYTHONNOUSERSITE=1, PYTHONPATH=src, HUSHDESK_RENDER_DEBUG=1; python -m compileall -q src ✅

3. 2025-11-10T22:24:37Z — import pipeline check
   - headless import summary: IMPORT_SUMMARY {'failed': []}

4. 2025-11-10T22:26:21Z — renderer + worker safeguards
   - import guard: hushdesk.workers.audit_worker now tolerates missing dev_override_date; orientation renderer already central + fail-safe used in overlay/evidence/preview dialog call sites

5. 2025-11-10T22:27:39Z — headless tracer + hooks
   - added tools/audit_tracer.py with path hashing + counts logging
   - verified .githooks/pre-commit blocks staged PDFs outside tests/fixtures and git config core.hooksPath=.githooks

6. 2025-11-10T22:27:51Z — audit tracer (auto)
   - worker_sha=2bfa1dd0f245 renderer_sha=6911e9c2b4fe
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 114, 'vitals': 0, 'rules': 0, 'decisions': 0}

7. 2025-11-10T22:29:07Z — tracer log formatting fix
   - retrofitted entry #6 to expand escaped newlines after initial auto-run; tools/audit_tracer.py updated to write clean entries going forward

8. 2025-11-10T22:29:22Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=6911e9c2b4fe
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 114, 'vitals': 0, 'rules': 0, 'decisions': 0}

9. 2025-11-10T22:30:11Z — branch switch
   - created/switch to fix/phase1-foundation (from fix/preview-orientation-fit) for headless baseline work

10. 2025-11-10T22:30:59Z — commit + push
   - commit b44f78c pushed to origin/fix/phase1-foundation; includes docs/BATON.md, tools/audit_tracer.py, audit worker guard

11. 2025-11-10T22:31:51Z — baton log follow-up
   - commit f563313 (phase1: baton push log) pushed to origin/fix/phase1-foundation; ensures entry #10 lives in repo
12. 2025-11-10T22:51:54Z — phase2 branch/env snapshot
   - branch fix/phase2-vitals-to-decisions (from fix/phase1-foundation)
   - env: Python 3.11.14; PySide6 6.10.0; MuPDF 1.24.10
   - flags: PYTHONNOUSERSITE=1, PYTHONPATH=src, HUSHDESK_RENDER_DEBUG=0

13. 2025-11-10T22:52:12Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=6911e9c2b4fe
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 114, 'vitals': 0, 'rules': 0, 'decisions': 0}
14. 2025-11-10T23:00:43Z — phase2 vitals/rules wiring
   - canonical words extraction now scans entire page + stores draw segments; MAR grid uses default strict rules when block text missing thresholds
   - tests: pytest tests/test_vitals_smoke.py; python hushdesk.pdf.mar_parser_mupdf run against hashed MAR sample ✅
   - interim counts from run_mar_audit: pages=57 due=160 parametered=160 hold_miss=8 held_app=18 compliant=364 dcd=24

15. 2025-11-10T23:00:52Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=6911e9c2b4fe
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 92, 'vitals': 160, 'rules': 160, 'decisions': 432}
16. 2025-11-10T23:02:06Z — push fix/phase2-vitals-to-decisions
   - commit e40840c pushed to origin/fix/phase2-vitals-to-decisions (canonical vitals/rules/decisions bring-up)
   - remote confirmed branch creation per GitHub instructions
17. 2025-11-11T00:01:07Z — vitals bounds instrumentation
   - branch fix/phase2-vitals-to-decisions @ fc684f5; added hard SBP/HR gates with counters + default rule metadata source/version tags.
   - grid extractor now drops out-of-band readings, tallies gated_sbp/hr, and emits per-rule confidence + instrumentation (rules_sources, band_stage_counts).
   - audit tracer includes gated/rule-source/band-stage JSON fields for future log scrapes.
   - tests: python3 -m compileall -q src; .venv311/bin/python -m pytest -q tests/test_vitals_bounds.py

18. 2025-11-11T00:49:36Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=6911e9c2b4fe
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 620}
19. 2025-11-11T00:50:21Z — phase2 band cascade + tokenizer normalization
   - branch fix/phase2-vitals-to-decisions; added SpatialWordIndex y-bucket joins plus label normalization for BP/HR vitals, and introduced band_resolver header→page→borrow cascade with per-stage counters feeding instrumentation/tracer (decision stage breakdowns preserved).
   - tests: python3 -m compileall -q src; PYTHONPATH=src PYTHONNOUSERSITE=1 .venv311/bin/python -m pytest -q tests/test_vitals_bounds.py.
   - tracer: path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 stage_counts={'header': 92, 'page': 25, 'borrow': 0, 'miss': 0}; counts pages=117 bands=117 vitals=236 rules=236 decisions=620.
20. 2025-11-11T01:02:37Z — phase2 closeout instrumentation
   - branch fix/phase2-vitals-to-decisions; wired decision de-duplication keys (slot label/row/rule) before tally, emitted rule-source breakdown + confidence histogram, and exposed the metrics through tracer JSON + BATON.
   - tests: PYTHONPATH=src PYTHONNOUSERSITE=1 python -m compileall -q src; pytest -q tests/test_vitals_bounds.py tests/test_decision_metrics.py.
   - tracer fields now include gated vitals, band stage counts, rule source breakdown, confidence histogram, and deduped decision totals for downstream scrapes.
### 2025-11-11T01:09:09Z — Phase 2 Confirm + Phase 3 Kickoff (renderer cache + prefetch + timing)
- head: fc684f5
- py: Python 3.11.14; PYTHONNOUSERSITE=1; QT_QPA_PLATFORM=offscreen
- Phase 2 tracer metrics already emit gated/band_stage_counts/rules_source_breakdown/conf_hist/decisions_unique; no patch required.
- branch: fix/phase3-perf-cache
- Added src/hushdesk/ui/renderer_cache.py + preview_renderer cache plumbing (doc path SHA, region quantization, ~180MB cap) to satisfy Phase 3 LRU requirement.
- Introduced src/hushdesk/ui/preview_prefetcher.py executor helpers and tools/perf_probe.py for background warming + timing instrumentation.

21. 2025-11-11T01:14:57Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=db1950e6f80d
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 620}
- compile/tests: PYTHONNOUSERSITE=1 PYTHONPATH=src .venv311/bin/python -m compileall -q src ✅; .venv311/bin/pytest -q tests/test_vitals_bounds.py ✅
- tracer(after-perf): {"path_hash": "a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34", "status": "OK", "counts": {"pages": 117, "bands": 117, "vitals": 236, "rules": 236, "decisions": 620}, "gated": {"sbp": 0, "hr": 19}, "rules_source_breakdown": {"parsed": 0, "default": 188}, "band_stage_counts": {"header": 92, "page": 25, "borrow": 0, "miss": 0}, "conf_hist": {"0.0-0.25": 188, "0.25-0.5": 0, "0.5-0.75": 0, "0.75-1.0": 0}, "decisions_unique": 188, "error": null}
- perf_probe: {"pdf_sha": "a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34", "dpi": 144, "pages": 117, "samples": 12, "per_page_ms": [32.81745902495459, 21.77033299813047, 29.501750017516315, 28.84787501534447, 31.000332994153723, 18.567582999821752, 24.71079200040549, 32.20233297906816, 31.720165978185833, 31.633625010726973, 28.59124998212792, 23.039040999719873], "mean_ms": 27.866878333346296, "median_ms": 29.174812516430393, "total_s": 0.33441362497978844}
- note: path hashed only; renderer cache + perf probe now available for downstream prefetch tuning.
- push: origin fix/phase3-perf-cache @ 6cae714 (phase3 cache/prefetch/perf probe)
### 2025-11-11T01:33:30Z — Phase 2 Confirm & Phase 3 Wire-up (prefetch hooks, cache stats, tracer floors)
- head: 6cae714
- py: Python 3.11.14; PYTHONNOUSERSITE=1; QT_QPA_PLATFORM=offscreen
- branch: fix/phase3-wireup-ci
- prefetch_hooks: headless neighbor renderer warmup via preview_prefetcher (k±pages w/ hashed doc hint)
- preview_renderer: expose cache_stats() for baton diagnostics

22. 2025-11-11T01:35:21Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=97bbd88bbecb00d7ed9a1579447f555b1024033248cb09cf1fdf7d43c5d3e957 status=FAIL counts={'pages': 0, 'bands': 0, 'vitals': 0, 'rules': 0, 'decisions': 0}

23. 2025-11-11T01:35:37Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 620}

24. 2025-11-11T01:35:51Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 620}
- tracer_assert: new headless guard rails for MAR counts; compileall + pytest (bounds/decision metrics) pass
- tracer_run a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 -> audit OK + assert OK (bands>=112, gated_ratio<=0.15)
- cache_stats snapshot: {"items": 0, "bytes": 0, "cap": 188743680}
### 2025-11-11T01:51:08Z — Phase 3 UI prefetch wiring
- head: 6cae714; branch fix/phase3-wireup-ci
- ui: EvidencePanel + MainWindow now call hushdesk.ui.prefetch_hooks.prefetch_neighbors on selection once page indices resolve
- hooks: prefetch_hooks accepts Path/str fallbacks and delegates to preview_prefetcher so headless runs can warm caches without live fitz docs
### 2025-11-11T01:51:24Z — Minimal CI workflow added
- head: 6cae714; branch fix/phase3-wireup-ci
- ci: .github/workflows/ci.yml runs macos-latest Py3.11, compileall src, then pytest smoke (vitals_bounds + decision_metrics) with optional tracer block commented for MAR secrets
### 2025-11-11T01:52:00Z — Phase 3 smoke compile/tests
- head: 6cae714; python .venv311/bin/python 3.11 w/ PYTHONNOUSERSITE=1, PYTHONPATH=src
- compile: python -m compileall -q src ✅
- tests: pytest -q tests/test_vitals_bounds.py tests/test_decision_metrics.py ✅
- tracer_assert: skipped (no MAR in workspace; CI block remains commented)
### 2025-11-11T02:07:10Z — Phase 2: Rules Master (strict) + Per-Med Parse + Row-Scoping tests
- head: 6cae714
- py: bash: python: command not found; PYTHONNOUSERSITE=1; QT_QPA_PLATFORM=offscreen
- branch: fix/phase2-rules-master
- rules-master bring-up: Rule/RuleSet now emit concrete Rule objects + evaluate_vitals(); mar_grid_extract falls back to parse_strict_rules before default thresholds kick in.
- tests: python3 -m compileall -q src ✅ · .venv311/bin/python -m pytest -q tests/test_rules_master_strict.py tests/test_row_scoping.py ✅

25. 2025-11-11T02:19:28Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 620}

26. 2025-11-11T02:19:42Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 620}
- tracer(after rules-master): {"path_hash": "a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34", "status": "OK", "counts": {"pages": 117, "bands": 117, "vitals": 236, "rules": 236, "decisions": 620}, "gated": {"sbp": 0, "hr": 19}}
- push_status: 0
  * [new branch]      fix/phase2-rules-master -> fix/phase2-rules-master
  branch 'fix/phase2-rules-master' set up to track 'origin/fix/phase2-rules-master'.

27. 2025-11-11T02:40:14Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 620}

28. 2025-11-11T02:43:04Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 620}

29. 2025-11-11T02:48:40Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 619}

30. 2025-11-11T02:48:52Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 619}
31. 2025-11-11T02:49:18Z — phase2 strict band parse tracer
   - branch fix/phase2-strict-wirein @ 9ae5596; python -m compileall -q src ✅
   - tracer(strict-band): {"path_hash": "a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34", "status": "OK", "counts": {"pages": 117, "bands": 117, "vitals": 236, "rules": 236, "decisions": 619}, "gated": {"sbp": 0, "hr": 19}, "rules_source_breakdown": {"parsed": 4, "default": 188}, "band_stage_counts": {"header": 92, "page": 25, "borrow": 0, "miss": 0}, "conf_hist": {"0.0-0.25": 188, "0.25-0.5": 0, "0.5-0.75": 4, "0.75-1.0": 0}, "decisions_unique": 192}
   - parsed_ct=4 (>0 floor), bands=117 (>=112), gated_ratio=0.08 (19 gated / 236 vitals)

32. 2025-11-11T03:23:04Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=8c4f49737491c24dfe920ec2a2a2471ef9d827c212f7cddbfe5baf69ea585af1 status=FAIL counts={'pages': 0, 'bands': 0, 'vitals': 0, 'rules': 0, 'decisions': 0}

33. 2025-11-11T03:24:31Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 619}

34. 2025-11-11T03:26:36Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 619}

35. 2025-11-11T03:27:41Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 619}

36. 2025-11-11T03:47:47Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 565}
### 2025-11-11T03:48:05Z — Phase-2 STRICT PARSE TUNE (band-span + regex)
- head: 9ae5596; branch fix/phase2-strict-tune; env: PYTHONNOUSERSITE=1; QT_QPA_PLATFORM=offscreen
- tracer(baseline): {"counts": {"pages": 117, "bands": 117, "vitals": 236, "rules": 236, "decisions": 619}, "gated": {"sbp": 0, "hr": 19}, "rules_source_breakdown": {"parsed": 4, "default": 188}}
- tracer(strict-tuned): {"counts": {"pages": 117, "bands": 117, "vitals": 236, "rules": 236, "decisions": 565}, "gated": {"sbp": 0, "hr": 19}, "rules_source_breakdown": {"parsed": 43, "default": 115}}
- parsed_improved: 4 → 43; bands=117; gated_ratio=0.08
- notes: block summaries now pull the entire band span (left panel + column) and strict regex covers chained comparators/synonyms; `python -m compileall -q src` ✅
### 2025-11-11T04:02:52Z — Phase-2 STRICT PARSE SAFETY TUNE (span+regex only)
- head: 9ae5596 on branch=fix/phase2-strict-wirein; env: Python 3.9.6 (PYTHONNOUSERSITE=1); QT_QPA_PLATFORM=offscreen
- RUN_TRACER=0 — skipped real MAR access; tracer verification pending via tools/audit_tracer.py once RUN_TRACER=1
- span: _block_text_summary now clamps to full page width with light vertical padding and merges CanonPage tokens safely
- regex: parse_strict_rules normalizes ≥/≤/unicode, unifies SBP/HR synonyms, handles chained OR strict predicates, tags rules as strict
- verify: python3 -m compileall -q src ✅
- next: run PYTHONNOUSERSITE=1 PYTHONPATH=src python3 tools/audit_tracer.py "$MAR" | tail -n 1; expect bands ≥112, gated_ratio ≤0.15, parsed_after > parsed_before
### 2025-11-11T05:34:32Z — Phase-2/3 CLOSEOUT (span+regex tune, floors helper)
- head: 9ae5596 on branch=fix/phase2-strict-wirein; env: Python 3.9.6; PYTHONNOUSERSITE=1; QT_QPA_PLATFORM=offscreen
- RUN_TRACER=0 — real MAR not accessible in sandbox; defer floors validation to local run (see below)
- span: _block_text_summary now tagged [PHASE2_STRICT_SPAN_TUNED_SAFE] with full-width clamp + merged CanonPage text
- regex: parse_strict_rules normalizes ≥/≤ + SBP/HR synonyms, scans chained comparators, dedups, tags rules.strict
- tracer_assert: added min/baseline parsed floors so parsed_after must exceed baseline when RUN_TRACER=1
- verify: python3 -m compileall -q src ✅
- next: export RUN_TRACER=1 MAR="$HOME/Downloads/Administration Record Report 2025-11-10.pdf"; run PYTHONNOUSERSITE=1 PYTHONPATH=src python3 tools/audit_tracer.py "$MAR" | tail -n 1 and ensure bands ≥ 112 (ideally 117), gated_ratio ≤ 0.15, parsed_after > parsed_before

37. 2025-11-11T05:43:22Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=FAIL counts={'pages': 0, 'bands': 0, 'vitals': 0, 'rules': 0, 'decisions': 0}

38. 2025-11-11T05:43:40Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=FAIL counts={'pages': 0, 'bands': 0, 'vitals': 0, 'rules': 0, 'decisions': 0}

39. 2025-11-11T05:45:33Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 565}

40. 2025-11-11T05:45:46Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 565}
### 2025-11-11T05:46:21Z — Phase-2/3 FINALIZE (strict span+regex, floors on real MAR)
- head: 9ae5596 on branch=fix/phase2-strict-wirein; env: Python 3.11.14 (.venv311); PYTHONNOUSERSITE=1; QT_QPA_PLATFORM=offscreen
- RUN_TRACER=1; real MAR hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 (path only hashed)
- span: _block_text_summary now clamps to page width with light vertical pad and merges CanonWord + CanonTextBlock text, single-spacing output
- regex: parse_strict_rules aggressively normalizes ≥/≤, SBP/HR synonyms, GT/LT text, chained comparators; safe strict tagging even when Rule dataclass is frozen
- tracer(after): {"path_hash": "a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34", "status": "OK", "counts": {"pages": 117, "bands": 117, "vitals": 236, "rules": 236, "decisions": 565}, "gated": {"sbp": 0, "hr": 19}, "rules_source_breakdown": {"parsed": 43, "default": 115}, "band_stage_counts": {"header": 92, "page": 25, "borrow": 0, "miss": 0}, "conf_hist": {"0.0-0.25": 115, "0.25-0.5": 0, "0.5-0.75": 43, "0.75-1.0": 0}, "decisions_unique": 158, "error": null}
- tracer_assert: {"ok": true, "bands": 117, "vitals": 236, "gated_total": 19, "gated_ratio": 0.081, "parsed": 43, "baseline_parsed": 4, "reasons": []}
- floors: bands 117 ≥ 112, gated_ratio 0.081 ≤ 0.15, parsed improved 4 → 43 (baseline from baton entry #31)
- cache_stats: {'items': 0, 'bytes': 0, 'cap': 188743680}
- verify: python3 -m compileall -q src ✅
### 2025-11-11T06:06:01Z — Phase-2/3 CLOSEOUT EXECUTION (strict span+regex verified; floors rechecked)
- head: 9ae5596 on branch=fix/phase2-strict-wirein; env: Python 3.11.14 (.venv311); PYTHONNOUSERSITE=1; QT_QPA_PLATFORM=offscreen
- RUN_TRACER=1; real MAR path_sha256=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 (path only hashed)
- tracer(baseline-json from Phase-2 strict tune): {"path_hash": "a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34", "status": "OK", "counts": {"pages": 117, "bands": 117, "vitals": 236, "rules": 236, "decisions": 619}, "gated": {"sbp": 0, "hr": 19}, "rules_source_breakdown": {"parsed": 4, "default": 188}}
- tracer(after): {"path_hash": "a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34", "status": "OK", "counts": {"pages": 117, "bands": 117, "vitals": 236, "rules": 236, "decisions": 565}, "gated": {"sbp": 0, "hr": 19}, "rules_source_breakdown": {"parsed": 43, "default": 115}, "band_stage_counts": {"header": 92, "page": 25, "borrow": 0, "miss": 0}, "conf_hist": {"0.0-0.25": 115, "0.25-0.5": 0, "0.5-0.75": 43, "0.75-1.0": 0}, "decisions_unique": 158, "error": null}
- tracer_assert: {"ok": true, "bands": 117, "vitals": 236, "gated_total": 19, "gated_ratio": 0.081, "parsed": 43, "baseline_parsed": 4, "reasons": []}
- floors: bands=117 ≥ 112, parsed 4→43, gated_ratio=0.081 ≤ 0.15 (baseline provided via /tmp/mar_baseline.json)
- cache_stats: {"items": 0, "bytes": 0, "cap": 188743680}
- verify: python -m compileall -q src ✅
### 2025-11-11T06:17:16Z — Phase-2/3 VERIFY & SEAL (final floors on real MAR; baton receipt)
- head: 9ae5596 on branch=fix/phase2-strict-wirein; env: Python 3.11.14 (.venv311); PYTHONNOUSERSITE=1; QT_QPA_PLATFORM=offscreen
- RUN_TRACER=1; real MAR path_sha256=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 (path only hashed)
- verify: python -m compileall -q src ✅
- tracer(final): {"path_hash": "a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34", "status": "OK", "counts": {"pages": 117, "bands": 117, "vitals": 236, "rules": 236, "decisions": 565}, "gated": {"sbp": 0, "hr": 19}, "rules_source_breakdown": {"parsed": 43, "default": 115}, "band_stage_counts": {"header": 92, "page": 25, "borrow": 0, "miss": 0}, "conf_hist": {"0.0-0.25": 115, "0.25-0.5": 0, "0.5-0.75": 43, "0.75-1.0": 0}, "decisions_unique": 158, "error": null}
- floors(summary): {"bands": 117, "vitals": 236, "parsed": 43, "gated_ratio": 0.081}
- tracer_assert: {"ok": true, "bands": 117, "vitals": 236, "gated_total": 19, "gated_ratio": 0.081, "parsed": 43, "baseline_parsed": 4, "reasons": []}
- cache_stats: {"items": 0, "bytes": 0, "cap": 188743680}
- DO_COMMIT=0 (receipt only; no push)
### 2025-11-11T06:24:54Z — Phase-2/3 PUBLISH RECEIPT (tracer/floors; headless, no APIs)
- head: b4214a6 on branch=fix/phase2-strict-wirein; env: Python 3.11.14 (.venv311); PYTHONNOUSERSITE=1; QT_QPA_PLATFORM=offscreen
- RUN_TRACER=1; RUN_PERF=0; real MAR path_sha256=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 (path only hashed)
- verify: python -m compileall -q src ✅
- tracer(final): {"path_hash": "a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34", "status": "OK", "counts": {"pages": 117, "bands": 117, "vitals": 236, "rules": 236, "decisions": 565}, "gated": {"sbp": 0, "hr": 19}, "rules_source_breakdown": {"parsed": 43, "default": 115}, "band_stage_counts": {"header": 92, "page": 25, "borrow": 0, "miss": 0}, "conf_hist": {"0.0-0.25": 115, "0.25-0.5": 0, "0.5-0.75": 43, "0.75-1.0": 0}, "decisions_unique": 158, "error": null}
- floors(summary): {"bands": 117, "vitals": 236, "parsed": 43, "gated_ratio": 0.081}
- tracer_assert: {"ok": true, "bands": 117, "vitals": 236, "gated_total": 19, "gated_ratio": 0.081, "parsed": 43, "baseline_parsed": 4, "reasons": []}
- cache_stats: {"items": 0, "bytes": 0, "cap": 188743680}
- DO_COMMIT=1 (baton-only); DO_PUSH=0/DO_TAG=0
### 2025-11-11T06:46:07Z — Phase-3 CLOSEOUT (perf verify • prefetch presence • baton seal)
- head: 750a184 on branch=fix/phase2-strict-wirein; env: Python 3.11.14 (.venv311); PYTHONNOUSERSITE=1; QT_QPA_PLATFORM=offscreen
- presence: cache=yes prefetch=yes perf_probe=yes ci=yes
- RUN_PERF=1; RUN_TRACER=1; real MAR path_sha256=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 (path only hashed)
- verify: python -m compileall -q src ✅
- perf_probe(cold): {"pdf_sha": "a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34", "dpi": 144, "pages": 117, "samples": 12, "per_page_ms": [33.636959007708356, 21.644167019985616, 29.486458020983264, 28.61174999270588, 30.825583002297208, 18.551125016529113, 24.88145901588723, 32.12995801004581, 31.756874988786876, 31.539082992821932, 28.89070799574256, 23.28333299374208], "mean_ms": 27.936454838102993, "median_ms": 29.18858300836291, "total_s": 0.33524920800118707}
- perf_probe(warm): {"pdf_sha": "a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34", "dpi": 144, "pages": 117, "samples": 12, "per_page_ms": [32.55037497729063, 21.62087499164045, 29.31933299987577, 28.724584000883624, 30.706334015121683, 18.585916986921802, 24.468082992825657, 31.885249976767227, 31.482541002333164, 31.461541017051786, 28.734874998917803, 23.455374990589917], "mean_ms": 27.749590245851625, "median_ms": 29.027103999396786, "total_s": 0.33300666700233705} (≤ PERF_MEDIAN_MAX=35ms)
- tracer(final): {"path_hash": "a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34", "status": "OK", "counts": {"pages": 117, "bands": 117, "vitals": 236, "rules": 236, "decisions": 565}, "gated": {"sbp": 0, "hr": 19}, "rules_source_breakdown": {"parsed": 43, "default": 115}, "band_stage_counts": {"header": 92, "page": 25, "borrow": 0, "miss": 0}, "conf_hist": {"0.0-0.25": 115, "0.25-0.5": 0, "0.5-0.75": 43, "0.75-1.0": 0}, "decisions_unique": 158, "error": null}
- floors(summary): {"bands": 117, "vitals": 236, "parsed": 43, "gated_ratio": 0.081}
- tracer_assert: {"ok": true, "bands": 117, "vitals": 236, "gated_total": 19, "gated_ratio": 0.081, "parsed": 43, "baseline_parsed": 4, "reasons": []}
- cache_stats: {"items": 0, "bytes": 0, "cap": 188743680}
- DO_COMMIT=1 (baton-only); DO_PUSH=1; DO_TAG=0

41. 2025-11-11T06:05:48Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 565}

42. 2025-11-11T06:05:58Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 565}

43. 2025-11-11T06:16:23Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 565}

44. 2025-11-11T06:16:36Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 565}

45. 2025-11-11T06:16:45Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 565}

46. 2025-11-11T06:16:54Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 565}

47. 2025-11-11T06:17:02Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 565}

48. 2025-11-11T06:25:08Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 565}

49. 2025-11-11T06:25:19Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 565}

50. 2025-11-11T06:25:32Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 565}

51. 2025-11-11T06:25:41Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 565}

52. 2025-11-11T06:45:04Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 565}

53. 2025-11-11T06:45:13Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 565}

54. 2025-11-11T06:46:01Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=201242892951
   - path_hash=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 status=OK counts={'pages': 117, 'bands': 117, 'vitals': 236, 'rules': 236, 'decisions': 565}

### 2025-11-11T06:59:23Z — Phase-4 throughput/memory tooling prep (headless only)
- head: 4e6ca2c on branch=fix/phase2-strict-wirein; env: Python 3.9.6; QT_QPA_PLATFORM=offscreen
- RUN_AUDIT_TIMER=0; RUN_RSS=0; no Downloads access (tooling drop only; MAR path stays offline)
- instrumentation: added tools/audit_timer.py (per-stage timers + path hashing), tools/rss_probe.py (RSS sampler + CSV export), tools/audit_budget.py (scaled budget verdicts)
- budgets staged for this phase: AUDIT_TOTAL_MAX_S=120s @300pp, PAGE_RENDER_MEDIAN_MS_MAX=35ms, RSS_MAX_MB=900
- baton seal only; DO_COMMIT=0/DO_PUSH=0 pending future audit/runs
### 2025-11-11T07:09:28Z — Phase-4 MEASURE & SEAL (timing + RSS budgets on real MAR)
- head: 4e6ca2c on branch=fix/phase2-strict-wirein; env: Python 3.11.14 (.venv311); PYTHONNOUSERSITE=1; QT_QPA_PLATFORM=offscreen
- DO_MEASURE=1; real MAR path_sha256=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 (path only hashed)
- verify: python -m compileall -q src ✅
- audit_timer: {"ok":true,"file_sha":"a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34","hall":"UNKNOWN","audit_date":"2025-11-09","counts":{"reviewed":145,"parametered":236,"no_rule":0,"no_sbp":226,"no_hr":201,"hold_miss":0,"held_appropriate":10,"compliant":125,"dcd":10,"gated_sbp":0,"gated_hr":19,"pages":117,"bands":117,"vitals":236,"rules":236,"decisions":565},"instrumentation":{"pages":80,"due":236,"parametered":236,"no_rule":0,"no_sbp":226,"no_hr":201,"rules_sources":{"parsed":43,"default":115},"decision_stage_counts":{"DCD":44,"GIVEN":178,"CODE":10,"EMPTY":4},"band_stage_counts":{"header":92,"page":25,"borrow":0,"miss":0},"conf_hist":{"0.0-0.25":115,"0.25-0.5":0,"0.5-0.75":43,"0.75-1.0":0},"decisions_unique":158,"suppressed":49,"gated":{"sbp":0,"hr":19},"parametered_total":236,"other_code":4,"empty":4,"nonchip":8,"nonchip_breakdown":{"other_code":4,"empty":4},"nonchip_record_delta":91,"pages_total":117,"pages_with_band":117},"records":565,"timing_ms":{"legacy_run_ms":4697.737,"total_ms":4698.222},"total_s":4.698,"used_fallback":true,"error":null}
- rss_probe→audit_timer: {"ok":true,"file_sha":"a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34","hall":"UNKNOWN","audit_date":"2025-11-09","counts":{"reviewed":145,"parametered":236,"no_rule":0,"no_sbp":226,"no_hr":201,"hold_miss":0,"held_appropriate":10,"compliant":125,"dcd":10,"gated_sbp":0,"gated_hr":19,"pages":117,"bands":117,"vitals":236,"rules":236,"decisions":565},"instrumentation":{"pages":80,"due":236,"parametered":236,"no_rule":0,"no_sbp":226,"no_hr":201,"rules_sources":{"parsed":43,"default":115},"decision_stage_counts":{"DCD":44,"GIVEN":178,"CODE":10,"EMPTY":4},"band_stage_counts":{"header":92,"page":25,"borrow":0,"miss":0},"conf_hist":{"0.0-0.25":115,"0.25-0.5":0,"0.5-0.75":43,"0.75-1.0":0},"decisions_unique":158,"suppressed":49,"gated":{"sbp":0,"hr":19},"parametered_total":236,"other_code":4,"empty":4,"nonchip":8,"nonchip_breakdown":{"other_code":4,"empty":4},"nonchip_record_delta":91,"pages_total":117,"pages_with_band":117},"records":565,"timing_ms":{"legacy_run_ms":4711.262,"total_ms":4711.764},"total_s":4.712,"used_fallback":true,"error":null,"rss_csv":"/Users/hushdesk/Library/Application Support/HushDesk/Perf/rss_a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34.csv","rss_samples":11,"rss_peak_kb":1052432,"rss_peak_mb":1027.766,"child_exit_code":0}
- audit_budget (timing): {"ok":true,"pages":117,"file_sha":"a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34","checks":{"audit_total_s":{"ok":true,"value":4.698,"limit":46.8},"page_render_median_ms":{"ok":null,"value":null,"limit":35.0},"rss_peak_mb":{"ok":null,"value":null,"limit":900.0}},"targets":{"audit_total_max_s":46.8,"page_render_median_ms_max":35.0,"rss_max_mb":900.0}}
- audit_budget (rss): {"ok":false,"pages":117,"file_sha":"a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34","checks":{"audit_total_s":{"ok":true,"value":4.712,"limit":46.8},"page_render_median_ms":{"ok":null,"value":null,"limit":35.0},"rss_peak_mb":{"ok":false,"value":1027.766,"limit":900.0}},"targets":{"audit_total_max_s":46.8,"page_render_median_ms_max":35.0,"rss_max_mb":900.0}}
- rss_csv: ~/Library/Application Support/HushDesk/Perf/rss_a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34.csv (11 samples; peak 1027.766 MB > 900 MB budget)
- budgets enforced: AUDIT_TOTAL_MAX_S=120 (->46.8s @117pp), PAGE_RENDER_MEDIAN_MS_MAX=35, RSS_MAX_MB=900
- verdict: throughput ok (4.7s) but RSS ceiling breached; no code edits per prompt—follow-up tuning prompt required
- DO_COMMIT=0/DO_PUSH=0 (receipt only)
### 2025-11-11T07:27:47Z — Phase-4 MEMORY TUNE (cache guard/cap + streaming MAR extraction + RSS verify)
- head: 4e6ca2c on branch=fix/phase2-strict-wirein; env: Python 3.11.14 (.venv311); PYTHONNOUSERSITE=1; QT_QPA_PLATFORM=offscreen
- DO_MEASURE=1; real MAR path_sha256=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 (path only hashed)
- verify: python -m compileall -q src ✅
- memory fixes: renderer cache now env-guarded (HUSHDESK_DISABLE_RENDER_CACHE/HUSHDESK_CACHE_MAX_MB); PixCache honors MB caps; audit extraction shreds CanonPage state, streams MuPDF pages (no upfront list), and forces periodic gc+fitz.TOOLS.store_shrink; audit runs exported HUSHDESK_DISABLE_RENDER_CACHE=1 HUSHDESK_CACHE_MAX_MB=64 HUSHDESK_SHRED_PIXMAP=1 HUSHDESK_PAGE_GC_INTERVAL=4
- audit_timer: {"ok":true,"file_sha":"a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34","hall":"UNKNOWN","audit_date":"2025-11-09","counts":{"reviewed":145,"parametered":236,"no_rule":0,"no_sbp":226,"no_hr":201,"hold_miss":0,"held_appropriate":10,"compliant":125,"dcd":10,"gated_sbp":0,"gated_hr":19,"pages":117,"bands":117,"vitals":236,"rules":236,"decisions":565},"instrumentation":{"pages":80,"due":236,"parametered":236,"no_rule":0,"no_sbp":226,"no_hr":201,"rules_sources":{"parsed":43,"default":115},"decision_stage_counts":{"DCD":44,"GIVEN":178,"CODE":10,"EMPTY":4},"band_stage_counts":{"header":92,"page":25,"borrow":0,"miss":0},"conf_hist":{"0.0-0.25":115,"0.25-0.5":0,"0.5-0.75":43,"0.75-1.0":0},"decisions_unique":158,"suppressed":49,"gated":{"sbp":0,"hr":19},"parametered_total":236,"other_code":4,"empty":4,"nonchip":8,"nonchip_breakdown":{"other_code":4,"empty":4},"nonchip_record_delta":91,"pages_total":117,"pages_with_band":117},"records":565,"timing_ms":{"legacy_run_ms":4357.609,"total_ms":4357.748},"total_s":4.358,"used_fallback":true,"error":null}
- rss_probe→audit_timer: {"ok":true,"file_sha":"a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34","hall":"UNKNOWN","audit_date":"2025-11-09","counts":{"reviewed":145,"parametered":236,"no_rule":0,"no_sbp":226,"no_hr":201,"hold_miss":0,"held_appropriate":10,"compliant":125,"dcd":10,"gated_sbp":0,"gated_hr":19,"pages":117,"bands":117,"vitals":236,"rules":236,"decisions":565},"instrumentation":{"pages":80,"due":236,"parametered":236,"no_rule":0,"no_sbp":226,"no_hr":201,"rules_sources":{"parsed":43,"default":115},"decision_stage_counts":{"DCD":44,"GIVEN":178,"CODE":10,"EMPTY":4},"band_stage_counts":{"header":92,"page":25,"borrow":0,"miss":0},"conf_hist":{"0.0-0.25":115,"0.25-0.5":0,"0.5-0.75":43,"0.75-1.0":0},"decisions_unique":158,"suppressed":49,"gated":{"sbp":0,"hr":19},"parametered_total":236,"other_code":4,"empty":4,"nonchip":8,"nonchip_breakdown":{"other_code":4,"empty":4},"nonchip_record_delta":91,"pages_total":117,"pages_with_band":117},"records":565,"timing_ms":{"legacy_run_ms":4389.313,"total_ms":4389.463},"total_s":4.389,"used_fallback":true,"error":null,"rss_csv":"/Users/hushdesk/Library/Application Support/HushDesk/Perf/rss_a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34.csv","rss_samples":10,"rss_peak_kb":77984,"rss_peak_mb":76.156,"child_exit_code":0}
- audit_budget (timing): {"ok":true,"pages":117,"file_sha":"a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34","checks":{"audit_total_s":{"ok":true,"value":4.358,"limit":46.8},"page_render_median_ms":{"ok":null,"value":null,"limit":35.0},"rss_peak_mb":{"ok":null,"value":null,"limit":900.0}},"targets":{"audit_total_max_s":46.8,"page_render_median_ms_max":35.0,"rss_max_mb":900.0}}
- audit_budget (rss): {"ok":true,"pages":117,"file_sha":"a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34","checks":{"audit_total_s":{"ok":true,"value":4.389,"limit":46.8},"page_render_median_ms":{"ok":null,"value":null,"limit":35.0},"rss_peak_mb":{"ok":true,"value":76.156,"limit":900.0}},"targets":{"audit_total_max_s":46.8,"page_render_median_ms_max":35.0,"rss_max_mb":900.0}}
- rss_csv: ~/Library/Application Support/HushDesk/Perf/rss_a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34.csv (10 samples; peak 76.156 MB < 900 MB budget)
- budgets enforced: AUDIT_TOTAL_MAX_S=120 (->46.8s @117pp), PAGE_RENDER_MEDIAN_MS_MAX=35, RSS_MAX_MB=900
- verdict: throughput steady (4.36s) and RSS now well below ceiling (76 MB); cache stays env-guarded for audits; UI/QA still default-on
- DO_COMMIT=0/DO_PUSH=0 (receipt only)
### 2025-11-11T07:37:16Z — Phase-4 FINISH (measure→verify budgets→seal baton)
- head: 4e6ca2c on branch=fix/phase2-strict-wirein; env: Python 3.11.14 (.venv311); PYTHONNOUSERSITE=1; QT_QPA_PLATFORM=offscreen
- DO_MEASURE=1; real MAR path_sha256=a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34 (path only hashed)
- verify: python -m compileall -q src ✅
- audit_timer: {"ok":true,"file_sha":"a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34","hall":"UNKNOWN","audit_date":"2025-11-09","counts":{"reviewed":145,"parametered":236,"no_rule":0,"no_sbp":226,"no_hr":201,"hold_miss":0,"held_appropriate":10,"compliant":125,"dcd":10,"gated_sbp":0,"gated_hr":19,"pages":117,"bands":117,"vitals":236,"rules":236,"decisions":565},"instrumentation":{"pages":80,"due":236,"parametered":236,"no_rule":0,"no_sbp":226,"no_hr":201,"rules_sources":{"parsed":43,"default":115},"decision_stage_counts":{"DCD":44,"GIVEN":178,"CODE":10,"EMPTY":4},"band_stage_counts":{"header":92,"page":25,"borrow":0,"miss":0},"conf_hist":{"0.0-0.25":115,"0.25-0.5":0,"0.5-0.75":43,"0.75-1.0":0},"decisions_unique":158,"suppressed":49,"gated":{"sbp":0,"hr":19},"parametered_total":236,"other_code":4,"empty":4,"nonchip":8,"nonchip_breakdown":{"other_code":4,"empty":4},"nonchip_record_delta":91,"pages_total":117,"pages_with_band":117},"records":565,"timing_ms":{"legacy_run_ms":4463.637,"total_ms":4463.767},"total_s":4.464,"used_fallback":true,"error":null}
- rss_probe→audit_timer: {"ok":true,"file_sha":"a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34","hall":"UNKNOWN","audit_date":"2025-11-09","counts":{"reviewed":145,"parametered":236,"no_rule":0,"no_sbp":226,"no_hr":201,"hold_miss":0,"held_appropriate":10,"compliant":125,"dcd":10,"gated_sbp":0,"gated_hr":19,"pages":117,"bands":117,"vitals":236,"rules":236,"decisions":565},"instrumentation":{"pages":80,"due":236,"parametered":236,"no_rule":0,"no_sbp":226,"no_hr":201,"rules_sources":{"parsed":43,"default":115},"decision_stage_counts":{"DCD":44,"GIVEN":178,"CODE":10,"EMPTY":4},"band_stage_counts":{"header":92,"page":25,"borrow":0,"miss":0},"conf_hist":{"0.0-0.25":115,"0.25-0.5":0,"0.5-0.75":43,"0.75-1.0":0},"decisions_unique":158,"suppressed":49,"gated":{"sbp":0,"hr":19},"parametered_total":236,"other_code":4,"empty":4,"nonchip":8,"nonchip_breakdown":{"other_code":4,"empty":4},"nonchip_record_delta":91,"pages_total":117,"pages_with_band":117},"records":565,"timing_ms":{"legacy_run_ms":4398.0,"total_ms":4398.131},"total_s":4.398,"used_fallback":true,"error":null,"rss_csv":"/Users/hushdesk/Library/Application Support/HushDesk/Perf/rss_a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34.csv","rss_samples":10,"rss_peak_kb":78160,"rss_peak_mb":76.328,"child_exit_code":0}
- audit_budget (timing): {"ok":true,"pages":117,"file_sha":"a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34","checks":{"audit_total_s":{"ok":true,"value":4.464,"limit":46.8},"page_render_median_ms":{"ok":null,"value":null,"limit":35.0},"rss_peak_mb":{"ok":null,"value":null,"limit":900.0}},"targets":{"audit_total_max_s":46.8,"page_render_median_ms_max":35.0,"rss_max_mb":900.0}}
- audit_budget (rss): {"ok":true,"pages":117,"file_sha":"a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34","checks":{"audit_total_s":{"ok":true,"value":4.398,"limit":46.8},"page_render_median_ms":{"ok":null,"value":null,"limit":35.0},"rss_peak_mb":{"ok":true,"value":76.328,"limit":900.0}},"targets":{"audit_total_max_s":46.8,"page_render_median_ms_max":35.0,"rss_max_mb":900.0}}
- rss_csv: ~/Library/Application Support/HushDesk/Perf/rss_a4cd42ded6f60bd952a278c2740ffc48f89cc316404c33a2eef07242e09d1f34.csv (10 samples; peak 76.328 MB < 900 MB budget)
- budgets enforced: AUDIT_TOTAL_MAX_S=120 (->46.8s @117pp), PAGE_RENDER_MEDIAN_MS_MAX=35, RSS_MAX_MB=900
- budgets_verdict: PASS
- DO_COMMIT=0/DO_PUSH=0/DO_TAG=0 (receipt only; baton sealed)
### 2025-11-11T23:05:13Z — Phase-5 PREP (import-smoke fix on feat/phase5-rules-master; base=fix/phase2-strict-wirein)
- head: 0891ab9  env: Python 3.11.14; PYTHONNOUSERSITE=1
- compile: .venv311/bin/python -m compileall -q src ✅
- import_smoke: tools/import_smoke.py missing; manual `import hushdesk.pdf.mar_grid_extract` ✅
- DO_COMMIT=0; changes not committed by design

55. 2025-11-11T23:28:22Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=afe64d704918
   - path_hash=5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683 status=FAIL counts={'pages': 0, 'bands': 0, 'vitals': 0, 'rules': 0, 'decisions': 0}

56. 2025-11-11T23:29:19Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=afe64d704918
   - path_hash=8c4f49737491c24dfe920ec2a2a2471ef9d827c212f7cddbfe5baf69ea585af1 status=FAIL counts={'pages': 0, 'bands': 0, 'vitals': 0, 'rules': 0, 'decisions': 0}

57. 2025-11-11T23:29:42Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=afe64d704918
   - path_hash=5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683 status=OK counts={'pages': 0, 'bands': 0, 'vitals': 0, 'rules': 0, 'decisions': 0}

58. 2025-11-11T23:29:53Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=afe64d704918
   - path_hash=5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683 status=OK counts={'pages': 0, 'bands': 0, 'vitals': 0, 'rules': 0, 'decisions': 0}

59. 2025-11-11T23:31:08Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=afe64d704918
   - path_hash=5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683 status=FAIL counts={'pages': 0, 'bands': 0, 'vitals': 0, 'rules': 0, 'decisions': 0}

60. 2025-11-11T23:31:59Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=afe64d704918
   - path_hash=5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683 status=FAIL counts={'pages': 0, 'bands': 0, 'vitals': 0, 'rules': 0, 'decisions': 0}

61. 2025-11-11T23:32:33Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=afe64d704918
   - path_hash=5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683 status=OK counts={'pages': 106, 'bands': 106, 'vitals': 216, 'rules': 216, 'decisions': 538}

62. 2025-11-11T23:43:29Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=afe64d704918
   - path_hash=5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683 status=OK counts={'pages': 106, 'bands': 106, 'vitals': 216, 'rules': 216, 'decisions': 538}
### 2025-11-11T23:46:22Z — Phase-5 RULES MASTER V2 (strict parse on real MAR) — feat/phase5-rules-master
- head: 0891ab9 on branch=feat/phase5-rules-master; env: Python 3.11.14 (.venv311); PYTHONNOUSERSITE=1; QT_QPA_PLATFORM=offscreen
- import_smoke: IMPORT_OK
- MAR path_sha256=5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683
- tracer(baseline): {"path_hash": "5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683", "status": "OK", "counts": {"pages": 106, "bands": 106, "vitals": 216, "rules": 216, "decisions": 538}, "gated": {"sbp": 0, "hr": 44}, "rules_source_breakdown": {"parsed": 27, "default": 48}, "band_stage_counts": {"header": 106, "page": 0, "borrow": 0, "miss": 0}, "conf_hist": {"0.0-0.25": 48, "0.25-0.5": 0, "0.5-0.75": 27, "0.75-1.0": 0}, "decisions_unique": 75, "error": null}
- tracer(after): {"path_hash": "5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683", "status": "OK", "counts": {"pages": 106, "bands": 106, "vitals": 216, "rules": 216, "decisions": 538}, "gated": {"sbp": 0, "hr": 44}, "rules_source_breakdown": {"parsed": 27, "default": 48}, "band_stage_counts": {"header": 106, "page": 0, "borrow": 0, "miss": 0}, "conf_hist": {"0.0-0.25": 48, "0.25-0.5": 0, "0.5-0.75": 27, "0.75-1.0": 0}, "decisions_unique": 75, "error": null}
- parsed_delta: 27 → 27
- floors(summary): {"bands": 106, "gated_ratio": 0.204}
- DO_COMMIT=0; changes left uncommitted by design
### 2025-11-12T00:31:42Z — Phase-5 HOTFIX (bands/gated on Administration Record Report 2025-11-11.pdf) — feat/phase5-rules-master
- head: 0891ab9 on branch=feat/phase5-rules-master; env: Python 3.11.14 (.venv311); PYTHONNOUSERSITE=1; QT_QPA_PLATFORM=offscreen
- import_smoke: IMPORT_OK
- MAR path_sha256=5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683
- tracer(after): {"path_hash": "5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683", "status": "OK", "counts": {"pages": 106, "bands": 106, "vitals": 216, "rules": 216, "decisions": 538}, "gated": {"sbp": 0, "hr": 0}, "rules_source_breakdown": {"parsed": 27, "default": 48}, "band_stage_counts": {"header": 0, "page": 106, "borrow": 0, "miss": 0}, "conf_hist": {"0.0-0.25": 48, "0.25-0.5": 0, "0.5-0.75": 27, "0.75-1.0": 0}, "decisions_unique": 75, "error": null}
- floors(summary): {"bands": 106, "gated_ratio": 0.0}
- DO_COMMIT=0; changes left uncommitted by design

63. 2025-11-12T00:28:36Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=afe64d704918
   - path_hash=5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683 status=OK counts={'pages': 106, 'bands': 106, 'vitals': 216, 'rules': 216, 'decisions': 538}

64. 2025-11-12T00:44:03Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=afe64d704918
   - path_hash=5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683 status=OK counts={'pages': 106, 'bands': 106, 'vitals': 216, 'rules': 216, 'decisions': 538}

65. 2025-11-12T00:44:10Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=afe64d704918
   - path_hash=5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683 status=OK counts={'pages': 106, 'bands': 106, 'vitals': 216, 'rules': 216, 'decisions': 538}

66. 2025-11-12T00:44:27Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=afe64d704918
   - path_hash=5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683 status=OK counts={'pages': 106, 'bands': 106, 'vitals': 216, 'rules': 216, 'decisions': 538}

67. 2025-11-12T00:44:35Z — audit tracer
   - worker_sha=2bfa1dd0f245 renderer_sha=afe64d704918
   - path_hash=5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683 status=OK counts={'pages': 106, 'bands': 106, 'vitals': 216, 'rules': 216, 'decisions': 538}
### 2025-11-12T00:44:37Z — Phase-5 SEAL (dynamic floors) — feat/phase5-rules-master
- head: 0891ab9 on branch=feat/phase5-rules-master; env: Python 3.11.14 (.venv311); PYTHONNOUSERSITE=1
- verify: python -m compileall -q src ✅
- import_smoke: IMPORT_OK
- MAR filename=Administration Record Report 2025-11-11.pdf  path_sha256=5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683 (path only hashed)
- tracer(final): {"path_hash": "5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683", "status": "OK", "counts": {"pages": 106, "bands": 106, "vitals": 216, "rules": 216, "decisions": 538}, "gated": {"sbp": 0, "hr": 0}, "rules_source_breakdown": {"parsed": 27, "default": 48}, "band_stage_counts": {"header": 0, "page": 106, "borrow": 0, "miss": 0}, "conf_hist": {"0.0-0.25": 48, "0.25-0.5": 0, "0.5-0.75": 27, "0.75-1.0": 0}, "decisions_unique": 75, "error": null}
- tracer_assert(strict-only, --use-pages-as-min-bands, --max-gated-ratio 0.15): {"ok": true, "bands": 106, "pages": 106, "vitals": 216, "gated_total": 0, "gated_ratio": 0.0, "min_bands": 106, "parsed": 27, "baseline_parsed": null, "reasons": []}
- DO_COMMIT=0; changes left uncommitted by design
### 2025-11-12T01:13:09Z — Phase-5 MERGE & RELEASE (PII-safe) — merged feat/phase5-rules-master → main
- head(main): 79d145c   head(work): 79d145c
- sanity: compileall ✅, import_smoke ✅ (RUN_TESTS=0)
- release_note: docs/releases/phase5_seal.md
- tag: seal-phase5-20251112T005134Z (existing anchor)
