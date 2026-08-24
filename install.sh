#!/usr/bin/env bash
set -euo pipefail

# PEP 668-safe installer for the local-first WSA CLI and MCP server.
# The project is installed into a repository-local virtual environment so the
# user's Homebrew/system Python is never modified. The venv can see existing
# host site packages so a preinstalled setuptools can be reused offline;
# WSA itself is still installed into the local environment.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WSA_ROOT="${WSA_ROOT:-$SCRIPT_DIR}"
WSA_VENV="${WSA_VENV_DIR:-$WSA_ROOT/.venv}"
WSA_PYTHON_BIN="${WSA_PYTHON_BIN:-python3}"

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]

Install WSA into a repository-local virtual environment, initialize the
SQLite database, and run the environment doctor.

Options:
  --venv PATH       Use PATH instead of .venv inside the repository.
  --python PATH     Use PATH to create the virtual environment.
  -h, --help        Show this help.

Environment overrides:
  WSA_ROOT          Trusted project checkout (defaults to this script's directory).
  WSA_VENV_DIR      Virtual environment path (defaults to $WSA_ROOT/.venv).
  WSA_PYTHON_BIN    Python 3.11+ executable (defaults to python3).
EOF
}

while (($# > 0)); do
  case "$1" in
    --venv)
      (($# >= 2)) || { echo "--venv requires a path" >&2; exit 2; }
      WSA_VENV="$2"
      shift 2
      ;;
    --python)
      (($# >= 2)) || { echo "--python requires an executable" >&2; exit 2; }
      WSA_PYTHON_BIN="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

WSA_ROOT="$(cd -- "$WSA_ROOT" && pwd)"

[[ -f "$WSA_ROOT/pyproject.toml" ]] || {
  echo "WSA checkout is missing pyproject.toml: $WSA_ROOT" >&2
  exit 1
}
command -v "$WSA_PYTHON_BIN" >/dev/null 2>&1 || {
  echo "Python executable not found: $WSA_PYTHON_BIN" >&2
  exit 1
}

if [[ "$WSA_VENV" != /* ]]; then
  WSA_VENV="$WSA_ROOT/$WSA_VENV"
fi
WSA_VENV="$($WSA_PYTHON_BIN -c 'import os, sys; print(os.path.abspath(sys.argv[1]))' "$WSA_VENV")"

"$WSA_PYTHON_BIN" - <<'PY'
import sys

if sys.version_info < (3, 11):
    raise SystemExit(
        f"WSA requires Python 3.11 or newer; found {sys.version_info.major}.{sys.version_info.minor}"
    )
print(f"Using Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
PY

if [[ ! -x "$WSA_VENV/bin/python" ]]; then
  if [[ -e "$WSA_VENV" ]]; then
    echo "Virtual environment path exists but is not usable: $WSA_VENV" >&2
    echo "Choose another path with --venv or remove that directory manually." >&2
    exit 1
  fi
  echo "Creating virtual environment: $WSA_VENV"
  "$WSA_PYTHON_BIN" -m venv --system-site-packages "$WSA_VENV"
fi

WSA_VENV_PYTHON="$WSA_VENV/bin/python"
echo "Installing WSA into the virtual environment..."
PIP_BUILD_FLAGS=()
if "$WSA_VENV_PYTHON" -c 'import setuptools' >/dev/null 2>&1; then
  PIP_BUILD_FLAGS+=(--no-build-isolation)
fi
"$WSA_VENV_PYTHON" -m pip install --disable-pip-version-check --no-input \
  "${PIP_BUILD_FLAGS[@]}" -e "$WSA_ROOT"

echo "Initializing the local SQLite database..."
(cd "$WSA_ROOT" && "$WSA_VENV_PYTHON" -m wsa.cli init)

echo "Running the WSA environment doctor..."
PATH="$WSA_VENV/bin:$PATH" "$WSA_VENV_PYTHON" \
  "$WSA_ROOT/agent/hermes/wechat-social-assistant/scripts/doctor.py" \
  --project-root "$WSA_ROOT"

cat <<EOF

WSA installation complete.

Virtual environment: $WSA_VENV
Database:            $WSA_ROOT/data/social.db

Start foreground WeChat capture:
  WSA_VENV_DIR="$WSA_VENV" "$WSA_ROOT/start.sh"

Check status without starting capture:
  WSA_VENV_DIR="$WSA_VENV" "$WSA_ROOT/start.sh" status

Start the MCP stdio server for an MCP host:
  WSA_VENV_DIR="$WSA_VENV" "$WSA_ROOT/start.sh" mcp
EOF
