"""Evidence/derived-fact accessors.

The OCR tables are acquisition evidence.  This module exposes the separate
candidate tables used by agents and human review, keeping confirmation state
out of the raw capture rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .store import connect, init_db


@dataclass(frozen=True)
class EvidenceSummary:
    perception_runs: int
    message_candidates: int
    participant_mentions: int
    relation_events: int
    pending_messages: int
    pending_mentions: int
    pending_events: int


def evidence_summary(db_path: Path | str) -> EvidenceSummary:
    init_db(db_path)
    with connect(db_path) as conn:
        counts = {
            table: int(conn.execute(f"select count(*) from {table}").fetchone()[0])
            for table in (
                "perception_runs",
                "message_candidates",
                "participant_mentions",
                "relation_events",
            )
        }
        pending = {
            "messages": int(conn.execute("select count(*) from message_candidates where status = 'candidate'").fetchone()[0]),
            "mentions": int(conn.execute("select count(*) from participant_mentions where status = 'candidate'").fetchone()[0]),
            "events": int(conn.execute("select count(*) from relation_events where status = 'candidate'").fetchone()[0]),
        }
    return EvidenceSummary(
        perception_runs=counts["perception_runs"],
        message_candidates=counts["message_candidates"],
        participant_mentions=counts["participant_mentions"],
        relation_events=counts["relation_events"],
        pending_messages=pending["messages"],
        pending_mentions=pending["mentions"],
        pending_events=pending["events"],
    )


def list_message_candidates(
    db_path: Path | str,
    *,
    status: str = "candidate",
    limit: int = 100,
) -> list[dict[str, Any]]:
    return _list_rows(
        db_path,
        """
        select m.*, c.captured_at, c.source, p.name as chat_name
        from message_candidates m
        join captures c on c.id = m.capture_id
        join people p on p.id = c.person_id
        where m.status = ?
        order by c.captured_at desc, m.id desc
        limit ?
        """,
        (status, max(1, int(limit))),
    )


def list_participant_mentions(
    db_path: Path | str,
    *,
    status: str = "candidate",
    limit: int = 100,
) -> list[dict[str, Any]]:
    return _list_rows(
        db_path,
        """
        select m.*, c.captured_at, c.source, p.name as chat_name
        from participant_mentions m
        join captures c on c.id = m.capture_id
        join people p on p.id = c.person_id
        where m.status = ?
        order by c.captured_at desc, m.id desc
        limit ?
        """,
        (status, max(1, int(limit))),
    )


def list_relation_events(
    db_path: Path | str,
    *,
    status: str = "candidate",
    limit: int = 100,
) -> list[dict[str, Any]]:
    return _list_rows(
        db_path,
        """
        select r.*, c.captured_at, c.source, chat.name as chat_name,
               person.name as person_name
        from relation_events r
        join captures c on c.id = r.capture_id
        join people chat on chat.id = c.person_id
        left join people person on person.id = r.person_id
        where r.status = ?
        order by coalesce(r.occurred_at, c.captured_at) desc, r.id desc
        limit ?
        """,
        (status, max(1, int(limit))),
    )


def _list_rows(db_path: Path | str, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]
