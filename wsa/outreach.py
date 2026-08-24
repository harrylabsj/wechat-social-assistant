"""Host-authored outreach drafts with an auditable status lifecycle.

WSA never sends messages.  A host agent (LLM) may draft personalised outreach
for a contact segment, but every draft lands in ``outreach_drafts`` as
``draft`` and only moves to ``approved`` when the user explicitly approves it
(panel or MCP with confirmation fields).  ``send_mode="computer_use"`` marks
drafts the user allows a computer-use-capable host to type into WeChat on
their behalf; ``manual`` drafts are copy-pasted by the user.  ``sent`` /
``dismissed`` close the loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .store import connect, init_db, now_iso


CREATE_CONFIRMATION_TEXT = "create outreach drafts"
UPDATE_CONFIRMATION_TEXT = "update outreach draft"
SEND_MODES = ("manual", "computer_use")
STATUSES = ("draft", "approved", "dismissed", "sent")
ACTIONS = ("approve", "dismiss", "edit", "mark_sent")


@dataclass(frozen=True)
class OutreachDraft:
    id: int
    person_name: str
    campaign: str
    topic: str
    draft_text: str
    send_mode: str
    status: str
    note: str
    created_at: str
    updated_at: str


def create_outreach_drafts(
    db_path: Path | str,
    *,
    items: list[dict[str, str]],
    campaign: str = "",
    topic: str = "",
    confirmed: bool = False,
    confirmation_text: str = "",
) -> list[OutreachDraft]:
    """Insert drafts authored by a host agent; every item needs a person."""

    _require_confirmation(confirmed, confirmation_text, CREATE_CONFIRMATION_TEXT)
    init_db(db_path)
    campaign = str(campaign or "").strip()
    topic = str(topic or "").strip()
    if not items:
        raise ValueError("items are required")
    timestamp = now_iso()
    created: list[OutreachDraft] = []
    with connect(db_path) as conn:
        for item in items:
            person_name = str(item.get("person_name") or "").strip()
            draft_text = str(item.get("draft_text") or "").strip()
            send_mode = str(item.get("send_mode") or "manual").strip()
            if not person_name or not draft_text:
                raise ValueError("each item needs person_name and draft_text")
            if send_mode not in SEND_MODES:
                raise ValueError(f"send_mode must be one of {SEND_MODES}")
            cursor = conn.execute(
                """
                insert into outreach_drafts
                (person_name, campaign, topic, draft_text, send_mode, status, note, created_at, updated_at)
                values (?, ?, ?, ?, ?, 'draft', '', ?, ?)
                """,
                (person_name, campaign, topic, draft_text, send_mode, timestamp, timestamp),
            )
            created.append(
                OutreachDraft(
                    id=int(cursor.lastrowid),
                    person_name=person_name,
                    campaign=campaign,
                    topic=topic,
                    draft_text=draft_text,
                    send_mode=send_mode,
                    status="draft",
                    note="",
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
        conn.commit()
    return created


def list_outreach_drafts(
    db_path: Path | str,
    *,
    status: str | None = None,
    campaign: str | None = None,
    person_name: str | None = None,
    limit: int = 200,
) -> list[OutreachDraft]:
    init_db(db_path)
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if campaign:
        clauses.append("campaign = ?")
        params.append(campaign)
    if person_name:
        clauses.append("person_name = ?")
        params.append(person_name)
    where = f"where {' and '.join(clauses)}" if clauses else ""
    params.append(max(1, min(1000, int(limit))))
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""
            select id, person_name, campaign, topic, draft_text, send_mode, status, note, created_at, updated_at
            from outreach_drafts
            {where}
            order by updated_at desc, id desc
            limit ?
            """,
            params,
        ).fetchall()
    return [_draft_from_row(row) for row in rows]


def update_outreach_draft(
    db_path: Path | str,
    *,
    draft_id: int,
    action: str,
    draft_text: str | None = None,
    note: str | None = None,
    confirmed: bool = False,
    confirmation_text: str = "",
) -> OutreachDraft:
    """Move one draft through approve/dismiss/edit/mark_sent."""

    _require_confirmation(confirmed, confirmation_text, UPDATE_CONFIRMATION_TEXT)
    init_db(db_path)
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {ACTIONS}")
    timestamp = now_iso()
    with connect(db_path) as conn:
        row = conn.execute(
            "select id, status from outreach_drafts where id = ?", (int(draft_id),)
        ).fetchone()
        if row is None:
            raise ValueError(f"outreach draft not found: {draft_id}")
        updates: list[str] = ["updated_at = ?"]
        params: list[Any] = [timestamp]
        if action == "approve":
            updates.append("status = 'approved'")
        elif action == "dismiss":
            updates.append("status = 'dismissed'")
        elif action == "mark_sent":
            updates.append("status = 'sent'")
        elif action == "edit":
            text = str(draft_text or "").strip()
            if not text:
                raise ValueError("draft_text is required for edit")
            updates.append("draft_text = ?")
            params.append(text)
        if note is not None:
            updates.append("note = ?")
            params.append(str(note))
        params.append(int(draft_id))
        conn.execute(f"update outreach_drafts set {', '.join(updates)} where id = ?", params)
        conn.commit()
    return _get_draft(db_path, int(draft_id))


def _get_draft(db_path: Path | str, draft_id: int) -> OutreachDraft:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            select id, person_name, campaign, topic, draft_text, send_mode, status, note, created_at, updated_at
            from outreach_drafts where id = ?
            """,
            (draft_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"outreach draft not found: {draft_id}")
    return _draft_from_row(row)


def outreach_to_dict(draft: OutreachDraft) -> dict[str, Any]:
    return {
        "id": draft.id,
        "person_name": draft.person_name,
        "campaign": draft.campaign,
        "topic": draft.topic,
        "draft_text": draft.draft_text,
        "send_mode": draft.send_mode,
        "status": draft.status,
        "note": draft.note,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
    }


def _require_confirmation(confirmed: bool, confirmation_text: str, expected: str) -> None:
    if confirmed is not True or confirmation_text != expected:
        raise ValueError(f'confirmed=true and confirmation_text="{expected}" are required')


def _draft_from_row(row) -> OutreachDraft:
    return OutreachDraft(
        id=int(row["id"]),
        person_name=row["person_name"],
        campaign=row["campaign"],
        topic=row["topic"],
        draft_text=row["draft_text"],
        send_mode=row["send_mode"],
        status=row["status"],
        note=row["note"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
