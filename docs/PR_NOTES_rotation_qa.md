# Rotation QA & Debug Summary

**Branch:** `test/preview-rotation-coverage`  
**Commit:** `1935f81` (expanded renderer instrumentation + rotation QA tests)

## What changed
- **Renderer (env-gated logging):** `src/hushdesk/ui/preview_renderer.py:7–61`
  - Added `HUSHDESK_RENDER_DEBUG` flag (`1/true/yes/on`) to trace render decisions without changing behavior.
  - Logs page `rotation`, `neutral`, `force_landscape`, `dpi/scale`, and output size after `transform_rect`.
  - Wrapped in `try/except` so logging can never break renders.

- **Tests added**
  - **Edge rotations:** `tests/test_preview_rotation_edges.py:1–34`
    - `/Rotate=270` on portrait → stays landscape after neutralize+policy.
    - `/Rotate=180` on landscape → remains landscape.
    - `/Rotate=0` portrait → forced landscape.
  - **Scale invariance:** `tests/test_preview_scale_invariance.py:1–14`
    - A 1-inch square in PDF space becomes exactly `target_dpi` pixels (guards matrix math).
  - **Rotation-lint (guardrail):** `tests/test_no_view_rotation.py:1–17`
    - Scans `src/` to block any return of `QGraphicsView.rotate(...)` / `.setRotation(...)`.

- **Headless verifier (optional):** `tools/verify_orientation.py`
  - Searches for **Administration Record Report 2025-11-07.pdf** (CWD/`./samples`/`~/Downloads`) and prints per-page landscape diagnostics.

## How to run
```bash
# activate clean venv
source .venv311/bin/activate
export PYTHONNOUSERSITE=1
export PYTHONPATH="$PWD/src"

# run targeted suite
pytest -q tests/test_preview_matrix.py \
          tests/test_preview_rotation_edges.py \
          tests/test_preview_scale_invariance.py \
          tests/test_no_view_rotation.py

# optional: headless PDF check (no GUI)
python tools/verify_orientation.py --name "Administration Record Report 2025-11-07.pdf"
````

## Optional debugging

```bash
export HUSHDESK_RENDER_DEBUG=1
# Run tests or verifier to see debug lines in logs
```

## Notes

* Untracked files untouched. Original automation had a quoting hiccup; changes landed as intended.
* Orientation is normalized at render time; overlays reuse the exact same matrix; view transform stays identity.

**Verdict:** Rotation behavior is now locked and test-guarded; debug logging is opt-in and safe.
