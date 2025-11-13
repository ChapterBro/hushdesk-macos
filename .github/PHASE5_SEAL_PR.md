**Phase-5 seal — strict-only comparators + dynamic floors**

- **Named MAR**: Administration Record Report 2025-11-11 (path SHA-256: 5e0bd408999ce713e0009dac53373869e670adf22ffdf64c10f059c0a0c36683)
- **Dynamic floors**: `bands ≥ pages` (tracer_assert `--use-pages-as-min-bands --max-gated-ratio 0.15`)
- **Expected**: bands = pages = 106, gated_ratio = 0.00, strict-only rules (<, >, LESS/GREATER, LT/GT; no equals, ≥/≤, above/below/over/under)
- **Scope**:
  - docs/BATON.md
  - tools/import_smoke.py
  - src/hushdesk/pdf/{band_resolver.py, mar_parser_mupdf.py, mar_tokens.py, time_slots.py, dates.py}
  - src/hushdesk/report/model.py
  - src/hushdesk/scout/
- **No PDFs in repo; no names in logs** (baton logs path hash only)
