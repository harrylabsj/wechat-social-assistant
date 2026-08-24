#!/usr/bin/env bash
set -euo pipefail

# Unified launcher. With no arguments it starts the explicit foreground
# capture loop. Other WSA CLI commands can be passed directly, e.g.
# ./start.sh status or ./start.sh dashboard.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WSA_ROOT="${WSA_ROOT:-$SCRIPT_DIR}"
WSA_VENV="${WSA_VENV_DIR:-$WSA_ROOT/.venv}"
WSA_CLI="$WSA_VENV/bin/wsa"
WSA_MCP="$WSA_VENV/bin/wsa-mcp"

usage() {
  cat <<'EOF'
Usage: ./start.sh [watch|mcp|wsa-command] [options]

Commands:
  (no command)  Start explicit foreground WeChat capture (watch).
  watch         Start explicit foreground WeChat capture.
  mcp           Start the stdio MCP server for a host process.
  status        Show local database and capture status.
  <wsa command> Pass any other command to the installed wsa CLI.

Examples:
  ./start.sh
  ./start.sh watch --interval 60
  ./start.sh status
  ./start.sh mcp
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || "${1:-}" == "help" ]]; then
  usage
  exit 0
fi

if [[ ! -x "$WSA_CLI" || ! -x "$WSA_MCP" ]]; then
  echo "WSA is not installed in $WSA_VENV" >&2
  echo "Run $WSA_ROOT/install.sh first." >&2
  exit 1
fi

WSA_ROOT="$(cd -- "$WSA_ROOT" && pwd)"
cd "$WSA_ROOT"

WSA_COMMAND="${1:-watch}"
if [[ "$WSA_COMMAND" == "mcp" ]]; then
  shift || true
  export WSA_ALLOWED_ROOT="${WSA_ALLOWED_ROOT:-$WSA_ROOT}"
  exec "$WSA_MCP" "$@"
fi

if [[ "$WSA_COMMAND" == "wsa" ]]; then
  shift || true
  exec "$WSA_CLI" "$@"
fi

if [[ $# -eq 0 ]]; then
  exec "$WSA_CLI" watch
fi

exec "$WSA_CLI" "$@"
