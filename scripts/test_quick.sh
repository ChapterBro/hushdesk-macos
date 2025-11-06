#!/usr/bin/env bash
set -Eeuo pipefail
. .venv_build/bin/activate || source .venv_build/bin/activate
start_ts=$(python - <<'PY'
import time; print(int(time.time()))
PY
)

# Run a focused, fast suite (adjust paths if tests absent)

PYTEST_CMD=("python" "-m" "pytest" "-q" \
"tests/test_rules_normalize.py" \
"tests/test_rules_parse.py" \
"tests/test_rulespec.py" \
"tests/test_duecell.py" \
"tests/test_rows.py" \
)
if ! "${PYTEST_CMD[@]}"; then
echo "PYTEST_FAIL" >&2
exit 2
fi
end_ts=$(python - <<'PY'
import time; print(int(time.time()))
PY
)
dur=$((end_ts - start_ts))
echo "PYTEST_OK duration=${dur}s"
