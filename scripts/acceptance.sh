#!/usr/bin/env bash
set -Eeuo pipefail
APP="${1:-dist/HushDesk.app}"
PLIST="$APP/Contents/Info.plist"
mkdir -p debug
echo "==> Verify plist keys" | tee debug/acceptance.txt
/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$PLIST" | tee -a debug/acceptance.txt
/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$PLIST" | tee -a debug/acceptance.txt
/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$PLIST" | tee -a debug/acceptance.txt
echo "==> CLI launch" | tee -a debug/acceptance.txt
EXECUTABLE=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$PLIST")
NSUnbufferedIO=YES "$APP/Contents/MacOS/$EXECUTABLE" > debug/launch_cli.log 2>&1 || true
echo "==> Finder launch with system logs" | tee -a debug/acceptance.txt
log stream --predicate 'process == "HushDesk" OR subsystem CONTAINS "LaunchServices"' --style compact --info > debug/launch_finder.log 2>&1 &
LOGPID=$!
sleep 1
open -n "$APP" || true
sleep 5
kill "$LOGPID" || true
osascript -e 'tell application "HushDesk" to quit' >/dev/null 2>&1 || true
echo "ACCEPTANCE: PASS" | tee -a debug/acceptance.txt
