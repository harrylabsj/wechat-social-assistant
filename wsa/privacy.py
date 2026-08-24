"""Local privacy controls for WSA evidence and exports.

The default workflow keeps raw evidence local, makes exported JSON redacted,
and requires explicit confirmation before retention cleanup.  Encryption is
delegated to the host's OpenSSL binary; the passphrase is read from stdin or
an environment variable and is never placed in process arguments.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any

from .store import connect, init_db, now_iso


DEFAULT_RETENTION_DAYS = 90
DEFAULT_PASSPHRASE_ENV = "WSA_BACKUP_PASSPHRASE"

_REDACTION_PATTERNS = (
    (re.compile(r"(?<!\d)(?:\+?86[ -]?)?1[3-9]\d{9}(?!\d)"), "[PHONE]"),
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "[EMAIL]"),
    (re.compile(r"\b(?:https?://|www\.)[^\s<>()]+", re.IGNORECASE), "[URL]"),
)

_TEXT_KEYS = {
    "raw_text",
    "clean_text",
    "corrected_text",
    "message_text",
    "evidence_excerpt",
    "preview",
    "notes",
    "note",
    "summary",
    "title",
    "text",
}
_PATH_KEYS = {"db_path", "image_path", "file_path"}


@dataclass(frozen=True)
class PrivacyPolicy:
    retention_days: int = DEFAULT_RETENTION_DAYS
    redact_exports: bool = True
    managed_images: bool = True
    encrypted_backups: bool = True


@dataclass(frozen=True)
class PurgeResult:
    db_path: Path
    cutoff: str
    matched_captures: int
    removed_captures: int
    removed_screenshots: int
    screenshot_paths: tuple[Path, ...]
    dry_run: bool


def redact_text(value: str) -> str:
    """Redact common direct identifiers while preserving readable context."""

    redacted = str(value)
    for pattern, replacement in _REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_payload(value: Any, *, key: str | None = None) -> Any:
    """Recursively redact text fields in a JSON-compatible export payload."""

    if isinstance(value, dict):
        return {name: redact_payload(item, key=name) for name, item in value.items()}
    if isinstance(value, list):
        return [redact_payload(item, key=key) for item in value]
    if isinstance(value, tuple):
        return [redact_payload(item, key=key) for item in value]
    if isinstance(value, str) and key in _PATH_KEYS:
        return Path(value).name or "[PATH]"
    if isinstance(value, str) and (key in _TEXT_KEYS or key is None):
        return redact_text(value)
    return value


def purge_expired_captures(
    db_path: Path | str,
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    as_of: str | None = None,
    dry_run: bool = True,
) -> PurgeResult:
    """Delete expired capture evidence and WSA-owned screenshots.

    User-imported images are never removed.  Foreign-key cascades clean the
    corresponding perception runs, OCR reviews, message candidates,
    participant mentions, and relation-event candidates with the capture.
    """

    try:
        days = int(retention_days)
    except (TypeError, ValueError) as exc:
        raise ValueError("retention_days must be an integer") from exc
    if days < 1:
        raise ValueError("retention_days must be >= 1")
    db = Path(db_path).expanduser().resolve(strict=False)
    init_db(db)
    cutoff = _cutoff_iso(days, as_of)
    with connect(db) as conn:
        rows = conn.execute(
            """
            select id, image_path, image_managed
            from captures
            where julianday(captured_at) < julianday(?)
            order by id
            """,
            (cutoff,),
        ).fetchall()
        capture_ids = [int(row["id"]) for row in rows]
        screenshots = _owned_unshared_images(conn, rows, db.parent / "captures")
        if not dry_run and capture_ids:
            placeholders = ", ".join("?" for _ in capture_ids)
            conn.execute(f"delete from captures where id in ({placeholders})", capture_ids)
            conn.commit()
    if not dry_run:
        for path in screenshots:
            path.unlink(missing_ok=True)
    return PurgeResult(
        db_path=db,
        cutoff=cutoff,
        matched_captures=len(capture_ids),
        removed_captures=0 if dry_run else len(capture_ids),
        removed_screenshots=0 if dry_run else len(screenshots),
        screenshot_paths=tuple(screenshots),
        dry_run=dry_run,
    )


def encrypted_backup_database(
    db_path: Path | str,
    encrypted_path: Path | str,
    *,
    passphrase: str | None = None,
    passphrase_env: str = DEFAULT_PASSPHRASE_ENV,
    overwrite: bool = False,
) -> Path:
    """Create an SQLite backup and encrypt it with OpenSSL AES-256-CBC.

    The plaintext SQLite snapshot exists only in a temporary file and is
    removed before returning.  ``passphrase`` is intended for tests; normal
    callers should use ``passphrase_env`` so secrets do not appear in shell
    history or process listings.
    """

    source = Path(db_path).expanduser().resolve(strict=False)
    target = Path(encrypted_path).expanduser().resolve(strict=False)
    if target.exists() and not overwrite:
        raise FileExistsError(f"encrypted backup already exists: {target}")
    secret = passphrase if passphrase is not None else os.environ.get(passphrase_env)
    if not secret:
        raise ValueError(f"set {passphrase_env} or passphrase explicitly before encrypting a backup")
    openssl = shutil.which("openssl")
    if not openssl:
        raise RuntimeError("openssl is required for encrypted backups")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_plaintext = tempfile.mkstemp(prefix="wsa-backup-", suffix=".db")
    os.close(fd)
    plain = Path(temporary_plaintext)
    temporary_output = target.with_name(f".{target.name}.tmp")
    try:
        from .store import backup_database

        backup_database(source, plain, overwrite=True)
        result = subprocess.run(
            [
                openssl,
                "enc",
                "-aes-256-cbc",
                "-pbkdf2",
                "-salt",
                "-pass",
                "stdin",
                "-in",
                str(plain),
                "-out",
                str(temporary_output),
            ],
            input=f"{secret}\n",
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "openssl encryption failed")
        if target.exists() and overwrite:
            target.unlink()
        temporary_output.replace(target)
    finally:
        plain.unlink(missing_ok=True)
        temporary_output.unlink(missing_ok=True)
    return target


def _cutoff_iso(retention_days: int, as_of: str | None) -> str:
    if as_of:
        value = str(as_of).replace("Z", "+00:00")
        try:
            reference = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("as_of must be an ISO timestamp") from exc
    else:
        reference = datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return (reference.astimezone(timezone.utc) - timedelta(days=retention_days)).isoformat(timespec="seconds")


def _owned_unshared_images(conn, rows, managed_root: Path) -> list[Path]:
    candidates: list[Path] = []
    capture_ids = [int(row["id"]) for row in rows]
    if not capture_ids:
        return candidates
    placeholders = ", ".join("?" for _ in capture_ids)
    for row in rows:
        if not row["image_path"] or not bool(row["image_managed"]):
            continue
        path = Path(str(row["image_path"])).expanduser().resolve(strict=False)
        try:
            path.relative_to(managed_root.expanduser().resolve(strict=False))
        except (OSError, ValueError):
            continue
        references = int(
            conn.execute(
                f"select count(*) from captures where image_path = ? and id not in ({placeholders})",
                [str(row["image_path"]), *capture_ids],
            ).fetchone()[0]
        )
        if references == 0 and path.is_file():
            candidates.append(path)
    return candidates
