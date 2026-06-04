#!/bin/zsh
set -euo pipefail

SCRIPT_PATH="${0:A}"
SCRIPT_DIR="${SCRIPT_PATH:h}"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"
CURRENT="$(
  python3 -m wsa.cli --db data/social.db watch-interval \
    | sed -n 's/^watch_interval_seconds=\([0-9][0-9]*\).*/\1/p'
)"
: "${CURRENT:=60}"
ANSWER="$(
  osascript -e "text returned of (display dialog \"WSA 扫描间隔（秒，最小 5）\" default answer \"$CURRENT\" buttons {\"取消\", \"保存\"} default button \"保存\")"
)"
OUTPUT="$(python3 -m wsa.cli --db data/social.db watch-interval "$ANSWER")"
printf '%s\n' "$OUTPUT"
osascript -e 'display notification "WSA 扫描间隔已更新" with title "WeChat Social Assistant"'
