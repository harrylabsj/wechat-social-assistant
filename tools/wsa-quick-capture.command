#!/bin/zsh
set -euo pipefail

SCRIPT_PATH="${0:A}"
SCRIPT_DIR="${SCRIPT_PATH:h}"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"
OUTPUT="$(python3 -m wsa.cli --db data/social.db quick-capture)"
printf '%s\n' "$OUTPUT"
osascript -e 'display notification "已完成一次 WSA 快捷采集" with title "WeChat Social Assistant"'
