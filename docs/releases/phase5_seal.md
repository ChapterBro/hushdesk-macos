# Phase-5 Seal — strict-only rules + dynamic floors (PII-safe)

**What’s in this seal**
- Strict parser accepts only `<`, `>`, "less than," "greater than," and `LT/GT` tokens.
- Dynamic floors enforce `bands ≥ pages` per MAR, with `gated_ratio ≤ 0.15` to keep vitals noise low.
- PII posture: no filenames or resident names logged; baton records the MAR path SHA-256 only.
- Scope confined to tools/docs guardrails (tracer assertor + seal trail); no PDFs enter version control.

**Verification summary**
- Import smoke: `IMPORT_OK`
- Quick tests: skipped (RUN_TESTS=0)
- Tracer/assert: floors green for the verified Administration Record (path_sha256=5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683)

**Tag**
- Release anchored at existing Phase-5 seal tag: `seal-phase5-20251112T005134Z`
