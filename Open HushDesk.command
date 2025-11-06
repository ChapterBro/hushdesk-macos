#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$DIR/dist/HushDesk.app"
xattr -dr com.apple.quarantine "$APP" || true
open -n "$APP"
