from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from .parser import Signal, extract_signals, parse_capture


class EmptyCaptureError(ValueError):
    pass


SCHEMA = """
create table if not exists people (
    id integer primary key autoincrement,
    name text not null unique,
    aliases_json text not null default '[]',
    notes text not null default '',
    created_at text not null,
    updated_at text not null,
    last_interaction_at text
);

create table if not exists captures (
    id integer primary key autoincrement,
    person_id integer not null references people(id) on delete cascade,
    captured_at text not null,
    source text not null,
    raw_text text not null,
    clean_text text not null,
    text_hash text not null,
    image_path text,
    created_at text not null,
    unique(person_id, text_hash)
);

create table if not exists capture_signals (
    id integer primary key autoincrement,
    capture_id integer not null references captures(id) on delete cascade,
    kind text not null,
    phrase text not null,
    unique(capture_id, kind)
);

create table if not exists contact_feedback (
    id integer primary key autoincrement,
    person_name text not null,
    action text not null,
    note text not null default '',
    until_at text,
    created_at text not null
);

create table if not exists relationship_candidates (
    id integer primary key autoincrement,
    name text not null,
    source_chat text not null,
    status text not null default 'pending',
    confidence integer not null,
    reasons_json text not null default '[]',
    evidence_captured_at text,
    evidence_excerpt text not null default '',
    icebreaker_draft text not null default '',
    created_at text not null,
    updated_at text not null,
    confirmed_at text,
    dismissed_at text,
    note text not null default '',
    unique(name, source_chat)
);

create table if not exists contact_enrichments (
    id integer primary key autoincrement,
    person_name text not null unique,
    source text not null default 'obsidian',
    fields_json text not null default '{}',
    raw_text text not null default '',
    file_path text,
    imported_at text not null,
    updated_at text not null
);

create index if not exists idx_people_last_interaction
on people(last_interaction_at);

create index if not exists idx_captures_person_time
on captures(person_id, captured_at);

create index if not exists idx_contact_feedback_person_time
on contact_feedback(person_name, created_at);

create index if not exists idx_relationship_candidates_status_confidence
on relationship_candidates(status, confidence);

create index if not exists idx_contact_enrichments_person
on contact_enrichments(person_name);
"""


@dataclass(frozen=True)
class IngestResult:
    capture_id: int
    person_id: int
    contact_name: str
    inserted: bool
    text_hash: str
    signal_kinds: tuple[str, ...]
    image_attached: bool = False


@dataclass(frozen=True)
class ResetResult:
    db_path: Path
    captures_dir: Path
    removed_people: int
    removed_captures: int
    removed_signals: int
    removed_feedback: int
    removed_candidates: int
    removed_enrichments: int
    removed_screenshots: int
    dry_run: bool = False


@dataclass(frozen=True)
class RefreshSignalsResult:
    capture_count: int
    signal_count: int


@dataclass(frozen=True)
class RefreshDerivedPeopleResult:
    capture_count: int


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def default_db_path(root: Path | None = None) -> Path:
    base = root or Path.cwd()
    return base / "data" / "social.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(db_path), factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    return conn


def init_db(db_path: Path | str) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        _migrate_existing_schema(conn)
        conn.commit()


def ingest_capture(
    db_path: Path | str,
    *,
    raw_text: str,
    contact_hint: str | None = None,
    source: str = "ocr",
    captured_at: str | None = None,
    image_path: str | None = None,
) -> IngestResult:
    init_db(db_path)
    captured_at = captured_at or now_iso()
    parsed = parse_capture(raw_text, contact_hint=contact_hint)
    if not parsed.clean_text.strip():
        raise EmptyCaptureError("empty capture text after OCR cleanup")
    text_hash = _hash_text(parsed.clean_text)
    current_time = now_iso()

    with connect(db_path) as conn:
        person_id = _ensure_person(conn, parsed.contact_name, current_time)
        existing = conn.execute(
            "select id, image_path from captures where person_id = ? and text_hash = ?",
            (person_id, text_hash),
        ).fetchone()
        if existing:
            image_attached = False
            if image_path and _should_attach_duplicate_image(existing["image_path"]):
                conn.execute(
                    """
                    update captures
                    set image_path = ?,
                        captured_at = ?,
                        source = ?,
                        raw_text = ?,
                        created_at = ?
                    where id = ?
                    """,
                    (image_path, captured_at, source, raw_text, current_time, int(existing["id"])),
                )
                image_attached = True
            if image_attached:
                _touch_person_interaction(conn, person_id, captured_at, current_time)
            _insert_capture_signals(conn, int(existing["id"]), parsed.signals)
            _ensure_group_speakers(conn, parsed.contact_name, parsed.lines, captured_at, current_time)
            conn.commit()
            return IngestResult(
                capture_id=int(existing["id"]),
                person_id=person_id,
                contact_name=parsed.contact_name,
                inserted=False,
                text_hash=text_hash,
                signal_kinds=tuple(signal.kind for signal in parsed.signals),
                image_attached=image_attached,
            )

        cursor = conn.execute(
            """
            insert into captures
            (person_id, captured_at, source, raw_text, clean_text, text_hash, image_path, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                person_id,
                captured_at,
                source,
                raw_text,
                parsed.clean_text,
                text_hash,
                image_path,
                current_time,
            ),
        )
        capture_id = int(cursor.lastrowid)
        _insert_capture_signals(conn, capture_id, parsed.signals)
        _touch_person_interaction(conn, person_id, captured_at, current_time)
        _ensure_group_speakers(conn, parsed.contact_name, parsed.lines, captured_at, current_time)
        conn.commit()

    return IngestResult(
        capture_id=capture_id,
        person_id=person_id,
        contact_name=parsed.contact_name,
        inserted=True,
        text_hash=text_hash,
        signal_kinds=tuple(signal.kind for signal in parsed.signals),
    )


def reset_memory(
    db_path: Path | str,
    *,
    captures_dir: Path | str | None = None,
    dry_run: bool = False,
) -> ResetResult:
    db = Path(db_path)
    screenshots = Path(captures_dir) if captures_dir is not None else db.parent / "captures"
    init_db(db)

    with connect(db) as conn:
        removed_people = int(conn.execute("select count(*) from people").fetchone()[0])
        removed_captures = int(conn.execute("select count(*) from captures").fetchone()[0])
        removed_signals = int(conn.execute("select count(*) from capture_signals").fetchone()[0])
        removed_feedback = int(conn.execute("select count(*) from contact_feedback").fetchone()[0])
        removed_candidates = int(conn.execute("select count(*) from relationship_candidates").fetchone()[0])
        removed_enrichments = int(conn.execute("select count(*) from contact_enrichments").fetchone()[0])
        if not dry_run:
            conn.execute("delete from capture_signals")
            conn.execute("delete from captures")
            conn.execute("delete from people")
            conn.execute("delete from contact_feedback")
            conn.execute("delete from relationship_candidates")
            conn.execute("delete from contact_enrichments")
            conn.commit()

    screenshot_files = _screenshot_files(screenshots)
    if not dry_run:
        for path in screenshot_files:
            path.unlink(missing_ok=True)

    return ResetResult(
        db_path=db,
        captures_dir=screenshots,
        removed_people=removed_people,
        removed_captures=removed_captures,
        removed_signals=removed_signals,
        removed_feedback=removed_feedback,
        removed_candidates=removed_candidates,
        removed_enrichments=removed_enrichments,
        removed_screenshots=len(screenshot_files),
        dry_run=dry_run,
    )


def refresh_capture_signals(db_path: Path | str) -> RefreshSignalsResult:
    init_db(db_path)
    with connect(db_path) as conn:
        captures = conn.execute("select id, clean_text from captures order by id").fetchall()
        conn.execute("delete from capture_signals")
        signal_count = 0
        for capture in captures:
            signals = extract_signals(capture["clean_text"])
            _insert_capture_signals(conn, int(capture["id"]), signals)
            signal_count += len(signals)
        conn.commit()

    return RefreshSignalsResult(capture_count=len(captures), signal_count=signal_count)


def refresh_derived_people(db_path: Path | str) -> RefreshDerivedPeopleResult:
    init_db(db_path)
    current_time = now_iso()
    with connect(db_path) as conn:
        captures = conn.execute(
            """
            select p.name as chat_name, c.clean_text, c.captured_at
            from captures c
            join people p on p.id = c.person_id
            order by c.captured_at asc, c.id asc
            """
        ).fetchall()
        for capture in captures:
            lines = [line.strip() for line in capture["clean_text"].splitlines() if line.strip()]
            _ensure_group_speakers(
                conn,
                capture["chat_name"],
                lines,
                capture["captured_at"],
                current_time,
            )
        conn.commit()

    return RefreshDerivedPeopleResult(capture_count=len(captures))


def _ensure_person(
    conn: sqlite3.Connection,
    name: str,
    current_time: str,
) -> int:
    existing = conn.execute("select id from people where name = ?", (name,)).fetchone()
    if existing:
        return int(existing["id"])

    cursor = conn.execute(
        """
        insert into people
        (name, aliases_json, notes, created_at, updated_at, last_interaction_at)
        values (?, ?, '', ?, ?, ?)
        """,
        (name, json.dumps([], ensure_ascii=False), current_time, current_time, None),
    )
    return int(cursor.lastrowid)


def _touch_person_interaction(
    conn: sqlite3.Connection,
    person_id: int,
    captured_at: str,
    current_time: str,
) -> None:
    conn.execute(
        """
        update people
        set updated_at = ?,
            last_interaction_at = case
                when last_interaction_at is null or last_interaction_at < ? then ?
                else last_interaction_at
            end
        where id = ?
        """,
        (current_time, captured_at, captured_at, person_id),
    )


def _should_attach_duplicate_image(existing_image_path: str | None) -> bool:
    if not existing_image_path:
        return True
    return not Path(existing_image_path).exists()


def _migrate_existing_schema(conn: sqlite3.Connection) -> None:
    _ensure_column(conn, "captures", "image_path", "text")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"pragma table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"alter table {table} add column {column} {definition}")


def _ensure_group_speakers(
    conn: sqlite3.Connection,
    chat_name: str,
    lines: list[str],
    captured_at: str,
    current_time: str,
) -> None:
    from .profiles import extract_speakers

    for speaker in extract_speakers(lines, chat_name=chat_name):
        speaker_id = _ensure_person(conn, speaker, current_time)
        _touch_person_interaction(conn, speaker_id, captured_at, current_time)


def _insert_capture_signals(conn: sqlite3.Connection, capture_id: int, signals: list[Signal]) -> None:
    conn.executemany(
        "insert or ignore into capture_signals (capture_id, kind, phrase) values (?, ?, ?)",
        ((capture_id, signal.kind, signal.phrase) for signal in signals),
    )


def _hash_text(text: str) -> str:
    stable = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def _screenshot_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    suffixes = {".png", ".jpg", ".jpeg", ".heic", ".tif", ".tiff"}
    return sorted(item for item in path.iterdir() if item.is_file() and item.suffix.lower() in suffixes)
