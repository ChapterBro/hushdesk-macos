#!/usr/bin/env bash
set -Eeuo pipefail
. .venv_build/bin/activate || source .venv_build/bin/activate
start_ts=$(python - <<'PY'
import time; print(int(time.time()))
PY
)

# Run a focused, fast suite (adjust paths if tests absent)

export PYTHONPATH=src

PYTEST_CMD=("python" "-m" "pytest" "-q" \
"tests/test_room_label.py" \
"tests/test_strict_gate.py" \
"tests/test_dedup.py" \
"tests/test_rules_normalize.py" \
"tests/test_rules_parse.py" \
"tests/test_rulespec.py" \
"tests/test_duecell.py" \
"tests/test_rows.py" \
)
tmp_log=$(mktemp -t hushdesk_pytest_XXXXXX)
if ! "${PYTEST_CMD[@]}" >"$tmp_log" 2>&1; then
cat "$tmp_log"
rm -f "$tmp_log"
echo "PYTEST_FAIL" >&2
exit 2
fi
rm -f "$tmp_log"
end_ts=$(python - <<'PY'
import time; print(int(time.time()))
PY
)
dur=$((end_ts - start_ts))
echo "PYTEST_OK duration=${dur}s"
