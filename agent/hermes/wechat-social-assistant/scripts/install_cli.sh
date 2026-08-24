#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WSA_ROOT="${WSA_PROJECT_ROOT:-$(cd -- "$SCRIPT_DIR/../../../.." && pwd)}"

if [[ -x "$WSA_ROOT/install.sh" ]]; then
  exec "$WSA_ROOT/install.sh" "$@"
fi

command -v git >/dev/null 2>&1 || {
  cat >&2 <<EOF
No trusted WSA checkout was found and git is unavailable.
Clone the repository, then run:

  cd /path/to/wechat-social-assistant
  ./install.sh
EOF
  exit 1
}

WSA_INSTALL_ROOT="${WSA_INSTALL_ROOT:-$HOME/.local/share/wechat-social-assistant}"
WSA_CHECKOUT="$WSA_INSTALL_ROOT/source"
if [[ ! -x "$WSA_CHECKOUT/install.sh" ]]; then
  if [[ -e "$WSA_CHECKOUT" ]]; then
    echo "Existing WSA install directory is not a valid checkout: $WSA_CHECKOUT" >&2
    exit 1
  fi
  mkdir -p "$WSA_INSTALL_ROOT"
  git clone "${WSA_REPOSITORY_URL:-https://github.com/harrylabsj/wechat-social-assistant.git}" \
    "$WSA_CHECKOUT"
fi

exec "$WSA_CHECKOUT/install.sh" "$@"
