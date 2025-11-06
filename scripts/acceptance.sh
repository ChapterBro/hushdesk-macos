#!/usr/bin/env bash
set -Eeuo pipefail
APP="${1:-dist/HushDesk.app}"
PDF_INPUT="${2:-}"
if [[ -z "$PDF_INPUT" ]]; then
  echo "Usage: $0 <APP_PATH> <PDF_INPUT>" >&2
  exit 2
fi

PDF_PATH=$(python - "$PDF_INPUT" <<'PY'
import os, sys
print(os.path.abspath(sys.argv[1]))
PY
)

PLIST="$APP/Contents/Info.plist"
mkdir -p debug
echo "==> Canonical matrix check" | tee -a debug/acceptance.txt
python3 -m hushdesk.pdf.debug_canon "/Users/hushdesk/Downloads/Administration Record Report 2025-11-05.pdf" | tee -a debug/acceptance.txt
echo "==> Verify plist keys" | tee debug/acceptance.txt
/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$PLIST" | tee -a debug/acceptance.txt
/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$PLIST" | tee -a debug/acceptance.txt
/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$PLIST" | tee -a debug/acceptance.txt
echo "==> CLI launch" | tee -a debug/acceptance.txt
EXECUTABLE=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$PLIST")
NSUnbufferedIO=YES "$APP/Contents/MacOS/$EXECUTABLE" > debug/launch_cli.log 2>&1 || true
echo "==> Headless audit" | tee -a debug/acceptance.txt
NSUnbufferedIO=YES "$APP/Contents/MacOS/$EXECUTABLE" \
  --headless \
  --input "$PDF_PATH" \
  --hall MERCER \
  --qa-png debug/qa_layout.png \
  > debug/acceptance_headless.log 2>&1
HEADLESS_STATUS=$?
if [[ $HEADLESS_STATUS -ne 0 ]]; then
  echo "Headless run failed (exit $HEADLESS_STATUS)" | tee -a debug/acceptance.txt
  exit $HEADLESS_STATUS
fi

TXT_PATH=$(awk -F': ' '/^TXT path:/ {print $2}' debug/acceptance_headless.log | tail -n 1)
if [[ -z "$TXT_PATH" || ! -f "$TXT_PATH" ]]; then
  echo "Headless run did not produce TXT output" | tee -a debug/acceptance.txt
  exit 3
fi

if [[ ! -f debug/qa_layout.png ]]; then
  echo "QA layout PNG missing" | tee -a debug/acceptance.txt
  exit 4
fi

echo "TXT output: $TXT_PATH" | tee -a debug/acceptance.txt
echo "QA PNG: debug/qa_layout.png" | tee -a debug/acceptance.txt
echo "==> Finder launch with system logs" | tee -a debug/acceptance.txt
log stream --predicate 'process == "HushDesk" OR subsystem CONTAINS "LaunchServices"' --style compact --info > debug/launch_finder.log 2>&1 &
LOGPID=$!
sleep 1
open -n "$APP" || true
sleep 5
kill "$LOGPID" || true
osascript -e 'tell application "HushDesk" to quit' >/dev/null 2>&1 || true
echo "ACCEPTANCE: PASS" | tee -a debug/acceptance.txt
