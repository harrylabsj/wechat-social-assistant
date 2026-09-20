from __future__ import annotations

import json
from dataclasses import dataclass
import os
import platform
from pathlib import Path
from typing import Any


DEFAULT_WATCH_INTERVAL_SECONDS = 60
MIN_WATCH_INTERVAL_SECONDS = 5
CAPTURES_DIR_ENV = "WSA_CAPTURES_DIR"

# WSA stores OCR'd WeChat conversations, chat screenshots and exports.  On a
# shared machine the process umask would otherwise leave all of it
# world-readable, which contradicts the product's local-privacy promise.
DATA_FILE_MODE = 0o600
DATA_DIR_MODE = 0o700


def secure_directory(path: Path | str) -> Path:
    """Create a data directory that only its owner can enter.

    Only for directories WSA itself owns (the data directory, the captures
    directory, the settings directory).  For the parent of a user-chosen
    output file (``backup --out``, ``export-data --out``) use
    :func:`ensure_output_directory` instead: chmod-ing a directory the user
    did not create would re-permission unrelated parts of their filesystem.
    """

    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        directory.chmod(DATA_DIR_MODE)
    except OSError:
        # A mounted volume (iCloud Drive, exFAT, a network share) may not
        # support POSIX modes.  Storage still works; the caller decides
        # whether a permissive filesystem is acceptable.
        pass
    return directory


def ensure_output_directory(path: Path | str) -> Path:
    """Create the parent directory of a user-chosen output file, without
    changing the permissions of a directory that already exists."""

    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def secure_file(path: Path | str) -> Path:
    """Restrict an existing data file to its owner."""

    target = Path(path)
    try:
        if target.exists():
            target.chmod(DATA_FILE_MODE)
    except OSError:
        pass
    return target
ICLOUD_DOCUMENTS_ROOT = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
ICLOUD_CAPTURE_RELATIVE = Path("codex") / "wechat-social-assistant" / "data" / "captures"


@dataclass(frozen=True)
class WSASettings:
    watch_interval_seconds: int = DEFAULT_WATCH_INTERVAL_SECONDS
    captures_dir: str | None = None


def settings_path_for_db(db_path: Path | str) -> Path:
    return Path(db_path).parent / "settings.json"


def load_settings(db_path: Path | str) -> WSASettings:
    path = settings_path_for_db(db_path)
    if not path.exists():
        return WSASettings()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return WSASettings()
    captures_dir = _normalize_captures_dir(payload.get("captures_dir"))
    return WSASettings(
        watch_interval_seconds=_coerce_interval(payload.get("watch_interval_seconds"), strict=False),
        captures_dir=str(captures_dir) if captures_dir is not None else None,
    )


def save_watch_interval(db_path: Path | str, seconds: int) -> WSASettings:
    interval = _coerce_interval(seconds, strict=True)
    current = load_settings(db_path)
    settings = WSASettings(watch_interval_seconds=interval, captures_dir=current.captures_dir)
    _write_settings(db_path, settings)
    return settings


def save_captures_dir(db_path: Path | str, captures_dir: Path | str | None) -> WSASettings:
    """Persist an explicit screenshot directory; ``None`` restores auto mode."""

    normalized = _normalize_captures_dir(captures_dir)
    current = load_settings(db_path)
    settings = WSASettings(
        watch_interval_seconds=current.watch_interval_seconds,
        captures_dir=str(normalized) if normalized is not None else None,
    )
    _write_settings(db_path, settings)
    return settings


def resolve_captures_dir(db_path: Path | str, override: Path | str | None = None) -> Path:
    """Resolve screenshot storage with explicit > env > settings > auto precedence.

    A relative ``WSA_CAPTURES_DIR`` is anchored at the database's directory,
    not the current working directory: watch and purge run as separate
    processes started from different directories, and a CWD-relative env
    value would make them disagree about where screenshots live.
    """

    if override not in (None, ""):
        return _normalize_captures_dir(override) or _local_captures_dir(db_path)
    env_value = os.environ.get(CAPTURES_DIR_ENV)
    if env_value:
        text = str(env_value).strip()
        if text and not Path(text).expanduser().is_absolute():
            anchor = Path(db_path).expanduser().resolve(strict=False).parent
            return (anchor / text).expanduser().resolve(strict=False)
        return _normalize_captures_dir(env_value) or _local_captures_dir(db_path)
    configured = load_settings(Path(db_path)).captures_dir
    if configured:
        return Path(configured)
    return default_captures_dir(db_path)


def capture_storage_roots(
    db_path: Path | str,
    override: Path | str | None = None,
) -> tuple[Path, ...]:
    """Return the active root plus the legacy checkout root, if different.

    A checkout may have captured screenshots before iCloud storage was
    enabled.  Keeping the old ``data/captures`` root as a read/cleanup
    compatibility root prevents those records from disappearing from status,
    the dashboard, retention cleanup, or contact deletion after the default
    root changes.  New captures always use the first (active) root.
    """

    active = resolve_captures_dir(db_path, override).expanduser().resolve(strict=False)
    legacy = _local_captures_dir(db_path).expanduser().resolve(strict=False)
    return (active,) if active == legacy else (active, legacy)


def default_captures_dir(db_path: Path | str) -> Path:
    """Return the automatic capture location for this checkout.

    On macOS checkouts with iCloud Drive mounted, screenshots go to the same
    iCloud project area used by the existing WSA installation.  A non-checkout
    database (including test databases) keeps the historical local path.
    """

    db = Path(db_path).expanduser().resolve(strict=False)
    project_root = db.parent.parent if db.parent.name == "data" else None
    if (
        platform.system() == "Darwin"
        and project_root is not None
        and (project_root / "pyproject.toml").is_file()
        and ICLOUD_DOCUMENTS_ROOT.is_dir()
    ):
        return (ICLOUD_DOCUMENTS_ROOT / ICLOUD_CAPTURE_RELATIVE).resolve(strict=False)
    return _local_captures_dir(db)


def _local_captures_dir(db_path: Path | str) -> Path:
    return Path(db_path).expanduser().resolve(strict=False).parent / "captures"


def _normalize_captures_dir(value: Any) -> Path | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    return Path(text).expanduser().resolve(strict=False)


def _write_settings(db_path: Path | str, settings: WSASettings) -> None:
    path = settings_path_for_db(db_path)
    secure_directory(path.parent)
    payload: dict[str, Any] = {"watch_interval_seconds": settings.watch_interval_seconds}
    if settings.captures_dir:
        payload["captures_dir"] = settings.captures_dir
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    secure_file(path)


def _coerce_interval(value: Any, *, strict: bool) -> int:
    try:
        interval = int(value)
    except (TypeError, ValueError):
        return DEFAULT_WATCH_INTERVAL_SECONDS
    if interval < MIN_WATCH_INTERVAL_SECONDS:
        if not strict:
            return DEFAULT_WATCH_INTERVAL_SECONDS
        raise ValueError(f"watch interval must be >= {MIN_WATCH_INTERVAL_SECONDS} seconds")
    return interval
