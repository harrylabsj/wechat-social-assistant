"""Local path policy used by the MCP transport boundary.

The CLI and Python API intentionally remain flexible because a user may keep
their database outside the checkout.  The MCP process is a different trust
boundary: tool arguments must not turn it into an arbitrary local file reader.
The launcher supplies ``WSA_MCP_ENFORCE_PATHS=1`` and a trusted
``WSA_ALLOWED_ROOT``; all file-like MCP arguments are then resolved below that
root (after symlink resolution).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .settings import resolve_captures_dir


class PathPolicyError(ValueError):
    """Raised when an MCP path escapes its configured trusted root."""


def mcp_path_policy_enabled() -> bool:
    value = os.environ.get("WSA_MCP_ENFORCE_PATHS", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def mcp_allowed_root(*, base: Path | str | None = None) -> Path:
    return mcp_allowed_roots(base=base)[0]


MEDIA_LABELS = frozenset({"captures_dir", "image_path", "media_path"})


def mcp_allowed_roots(
    *,
    base: Path | str | None = None,
    include_capture_root: bool = True,
) -> tuple[Path, ...]:
    """Return the configured roots, plus the capture root for media paths only.

    WSA may intentionally keep screenshots in an iCloud directory outside the
    checkout, so capture/media arguments may resolve there.  Everything else
    (databases, exports, backups) stays inside ``WSA_ALLOWED_ROOT``: a capture
    directory is not a general-purpose write target.
    """

    configured = os.environ.get("WSA_ALLOWED_ROOT")
    if configured:
        roots = [Path(item).expanduser() for item in configured.split(os.pathsep) if item]
    else:
        roots = [Path(base or Path.cwd())]
    if base is not None and include_capture_root:
        base_path = Path(base).expanduser()
        db_candidate = base_path if base_path.name == "social.db" else base_path / "social.db"
        roots.append(resolve_captures_dir(db_candidate))
    deduped: list[Path] = []
    for root in roots:
        resolved = root.resolve(strict=False)
        if resolved not in deduped:
            deduped.append(resolved)
    return tuple(deduped)


def resolve_mcp_path(
    value: Any,
    *,
    default: Path | str,
    label: str,
    base: Path | str | None = None,
) -> Path:
    """Resolve an MCP path and enforce the launcher-provided root when enabled."""

    candidate = Path(str(value)).expanduser() if value not in (None, "") else Path(default)
    resolved = candidate.resolve(strict=False)
    if not mcp_path_policy_enabled():
        return resolved

    roots = mcp_allowed_roots(base=base, include_capture_root=label in MEDIA_LABELS)
    if not any(_is_relative_to(resolved, root) for root in roots):
        joined = ", ".join(str(root) for root in roots)
        raise PathPolicyError(f"{label} must stay under a configured trusted root ({joined})")
    return resolved


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def configure_mcp_path_policy(*, root: Path | str | None = None) -> Path:
    """Enable the default stdio policy for a standalone MCP process.

    Without an explicit root the policy falls back to the selected database's
    directory rather than the working directory: launching ``wsa-mcp`` from
    ``~`` would otherwise make the entire home directory a trusted root for
    every path argument.
    """

    from .store import default_db_path

    configured = root or os.environ.get("WSA_ALLOWED_ROOT")
    if configured:
        allowed = Path(configured).expanduser().resolve(strict=False)
    else:
        allowed = Path(default_db_path(Path.cwd())).expanduser().resolve(strict=False).parent
    os.environ["WSA_ALLOWED_ROOT"] = str(allowed)
    # Force-set, not setdefault: a stale WSA_MCP_ENFORCE_PATHS=0 inherited
    # from the environment would otherwise keep the whole boundary disabled
    # while this function reports that it enabled it.
    os.environ["WSA_MCP_ENFORCE_PATHS"] = "1"
    return allowed
