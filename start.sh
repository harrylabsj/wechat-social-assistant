#!/usr/bin/env bash
set -euo pipefail

# Unified launcher. With no arguments it starts the explicit foreground
# capture loop. Other WSA CLI commands can be passed directly, e.g.
# ./start.sh status, ./start.sh dashboard, ./start.sh ui, or
# ./start.sh captures-dir.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WSA_ROOT="${WSA_ROOT:-$SCRIPT_DIR}"
WSA_VENV="${WSA_VENV_DIR:-$WSA_ROOT/.venv}"
WSA_PYTHON="$WSA_VENV/bin/python"

usage() {
  cat <<'EOF'
Usage: ./start.sh [watch|mcp|wsa-command] [options]

Commands:
  (no command)  Start explicit foreground WeChat capture (watch).
  watch         Start explicit foreground WeChat capture.
  mcp           Start the stdio MCP server for a host process.
  status        Show local database and capture status.
  ui            Open the local contact-centric CRM dashboard.
  captures-dir  Show or configure screenshot storage (macOS defaults to iCloud when available).
  <wsa command> Pass any other command to the installed wsa CLI.

Examples:
  ./start.sh
  ./start.sh watch --interval 60
  ./start.sh status
  ./start.sh ui
  ./start.sh captures-dir
  ./start.sh mcp
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || "${1:-}" == "help" ]]; then
  usage
  exit 0
fi

if [[ ! -x "$WSA_PYTHON" ]]; then
  echo "WSA is not installed in $WSA_VENV" >&2
  echo "Run $WSA_ROOT/install.sh first." >&2
  exit 1
fi

WSA_ROOT="$(cd -- "$WSA_ROOT" && pwd)"
cd "$WSA_ROOT"

# Run the checkout itself instead of relying on a possibly stale console
# script/site-package entry. This keeps a source checkout and its local venv
# on the same revision after an editable install or a source update.
export PYTHONPATH="$WSA_ROOT${PYTHONPATH:+:$PYTHONPATH}"

WSA_COMMAND="${1:-watch}"
if [[ "$WSA_COMMAND" == "mcp" ]]; then
  shift || true
  export WSA_ALLOWED_ROOT="${WSA_ALLOWED_ROOT:-$WSA_ROOT}"
  exec "$WSA_PYTHON" -m wsa.mcp_server "$@"
fi

if [[ "$WSA_COMMAND" == "wsa" ]]; then
  shift || true
  exec "$WSA_PYTHON" -m wsa.cli "$@"
fi

if [[ $# -eq 0 ]]; then
  exec "$WSA_PYTHON" -m wsa.cli watch
fi

exec "$WSA_PYTHON" -m wsa.cli "$@"
