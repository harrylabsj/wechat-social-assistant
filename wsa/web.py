"""Local CRM dashboard for extracted WeChat contacts.

The dashboard deliberately uses a small stdlib HTTP server instead of adding a
web framework or a frontend build.  It binds to loopback only and opens the
SQLite database in read-only mode for every view.  The page is
contact-centric: it shows which contacts were extracted and, for each
contact, a time-ordered timeline of distilled conversation summaries.  Raw
OCR observations stay in SQLite as evidence and are not rendered as the
primary view.  The single write route (`POST /api/enrichment`) lets the user
maintain a contact's 分类/标签/备注 in `contact_enrichments`; everything else
(capture, correction, deletion, messaging) still goes through the explicit
CLI/MCP confirmation paths.
"""

from __future__ import annotations

from datetime import datetime, timezone
from contextlib import closing
from collections import defaultdict
import json
import mimetypes
import os
from pathlib import Path
import re
import socket
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse
import webbrowser

from .connectors import connector_statuses
from .enrichment import record_contact_enrichment
from .outreach import UPDATE_CONFIRMATION_TEXT, outreach_to_dict, update_outreach_draft
from .parser import extract_signals
from .profiles import (
    build_profiles,
    important_content_lines,
    is_group_chat_name,
    speaker_message_map,
)
from .settings import capture_storage_roots, resolve_captures_dir
from .status import _process_rows, detect_watch_processes
from .store import connect
from .suggestions import build_suggestions


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8788
LOW_CONFIDENCE_THRESHOLD = 0.75
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".heic", ".tif", ".tiff"}
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

# The OCR stream contains UI labels and generated text that can look like a
# person name.  They are useful in the evidence layer, but should not become
# CRM contacts.  Keep this filter deliberately conservative: nicknames such as
# “老婆” are valid contacts and therefore remain visible.
CRM_NOISE_NAME_RE = re.compile(
    r"(?:积分|充值|兑换码|有效期|购买|赠送|ChatGPT|GPT|Cronjob|Pro[〉>]|账户|状态|来源|搜索|发送|聊天信息"
    r"|取消|转发|置顶|放大阅读|用窗口打开|条记录|条新消息|共\d*条|撤回|拍了拍|展开全部|免费|刚睡醒|深有同感)",
    re.IGNORECASE,
)
CRM_NOISE_PHRASES = {
    "就和我说",
    "大家都喜欢",
    "当前积分（+）",
    "总积分（+）",
    "活动赠送",
    "购买0．赠送 100",
    "工心士",
    "真大佬",
    "未知联系人",
    "微信会话列表",
}
CRM_FILLER_NAMES = {
    "嗯嗯",
    "好的",
    "谢谢",
    "感谢",
    "哈哈",
    "哈哈哈",
    "是的",
    "收到",
    "了解",
    "明白",
    "可以",
    "非常好",
    "不错",
}
# Group-speaker names come from fragile OCR heuristics, so they get stricter
# structural rules: checkbox glyphs, brackets and circled numbers (“⑤”, “K）”,
# “init_gift_76 口”) mark a UI artifact rather than a relationship.
CRM_SPEAKER_JUNK_CHARS = "口［【（(〈《〉》）)⋯◎©®§~^_、…．①②③④⑤⑥⑦⑧⑨⑩"
# Lines that are WeChat UI chrome or IME/pinyin candidate lists, not
# conversation content worth distilling into a CRM summary.
CRM_CONTENT_NOISE_RE = re.compile(
    r"(?:撤回了一条|撤回了.{0,6}消息|拍了拍|\d+\s*条新消息|[［\[]\s*\d+\s*条[］\]]|用窗口打开|展开全部|以上是打招呼的消息"
    r"|[a-zA-Z'’]+\s*\d?\s*1\s*[.、．]\s*[一-鿿])"  # 拼音候选词列表，如 “ba 1.把 2.吧”
)
CRM_GRAMMAR_LINE_RE = re.compile(
    r"^(?:命令式|祈使句|疑问句|陈述句|感叹句|反问句|被动句)"
    r"(?:\s+(?:命令式|祈使句|疑问句|陈述句|感叹句|反问句|被动句))*$"
)
CRM_CONTENT_NOISE_LINES = {
    "删除",
    "翻译",
    "取消",
    "转发",
    "置顶",
    "复制",
    "收藏",
    "多选",
    "引用",
    "提醒",
    "搜一搜",
    "用窗口打开",
    "展开全部",
    "返回",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _read_connection(db_path: Path) -> sqlite3.Connection:
    """Open an existing database without creating files or running migrations."""

    uri = f"{db_path.expanduser().resolve(strict=False).as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=2.0)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma query_only = on")
    conn.execute("pragma busy_timeout = 2000")
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "select 1 from sqlite_master where type = 'table' and name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _count(conn: sqlite3.Connection, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"select count(*) from {table}").fetchone()[0])


def _count_screenshots(captures_dir: Path) -> int:
    if not captures_dir.is_dir():
        return 0
    return sum(
        1
        for item in captures_dir.iterdir()
        if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES
    )


def _tail_line(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 8192))
            lines = handle.read().decode("utf-8", errors="replace").splitlines()
        return lines[-1] if lines else None
    except OSError:
        return None


def _line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        with path.open("rb") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_float(value: Any) -> float | None:
    number = _number(value)
    return round(number, 4) if number is not None else None


def _confidence_buckets(conn: sqlite3.Connection) -> tuple[list[dict[str, Any]], float | None, int]:
    empty = [
        {"key": "unknown", "label": "未知", "min": None, "max": None, "count": 0},
        {"key": "0-29", "label": "0–0.29", "min": 0.0, "max": 0.29, "count": 0},
        {"key": "30-49", "label": "0.30–0.49", "min": 0.30, "max": 0.49, "count": 0},
        {"key": "50-74", "label": "0.50–0.74", "min": 0.50, "max": 0.74, "count": 0},
        {"key": "75-89", "label": "0.75–0.89", "min": 0.75, "max": 0.89, "count": 0},
        {"key": "90-100", "label": "0.90–1.00", "min": 0.90, "max": 1.0, "count": 0},
    ]
    if not _table_exists(conn, "ocr_observations"):
        return empty, None, 0
    rows = conn.execute("select confidence from ocr_observations").fetchall()
    known: list[float] = []
    for row in rows:
        value = _number(row["confidence"])
        if value is None:
            empty[0]["count"] += 1
            continue
        value = max(0.0, min(1.0, value))
        known.append(value)
        if value < 0.30:
            empty[1]["count"] += 1
        elif value < 0.50:
            empty[2]["count"] += 1
        elif value < 0.75:
            empty[3]["count"] += 1
        elif value < 0.90:
            empty[4]["count"] += 1
        else:
            empty[5]["count"] += 1
    average = round(sum(known) / len(known), 4) if known else None
    return empty, average, len(known)


def _source_counts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "ocr_observations"):
        return []
    rows = conn.execute(
        "select coalesce(nullif(source, ''), 'unknown') as source, count(*) as count "
        "from ocr_observations group by source order by count desc, source"
    ).fetchall()
    return [{"source": str(row["source"]), "count": int(row["count"])} for row in rows]


def _current_signal_count(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "captures"):
        return 0
    rows = conn.execute("select coalesce(corrected_text, clean_text) as text from captures").fetchall()
    return sum(len(extract_signals(str(row["text"] or ""))) for row in rows)


def _managed_image_path(
    image_path: str | None,
    captures_dir: Path,
    *,
    db_path: Path | None = None,
) -> Path | None:
    """Return an image only when it resolves inside an active WSA root.

    ``db_path`` enables the legacy local root during the iCloud transition;
    imported images outside both managed roots remain hidden.
    """

    if not image_path:
        return None
    try:
        candidate = Path(image_path).expanduser()
        if not candidate.is_absolute():
            candidate = captures_dir / candidate
        candidate = candidate.resolve(strict=False)
        roots = capture_storage_roots(db_path, captures_dir) if db_path is not None else (captures_dir,)
        if not any(_is_relative_to(candidate, root) for root in roots):
            return None
    except (OSError, ValueError):
        return None
    if not candidate.is_file() or candidate.suffix.lower() not in IMAGE_SUFFIXES:
        return None
    return candidate


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root.expanduser().resolve(strict=False))
    except (OSError, ValueError):
        return False
    return True


def _preview(text: str | None, limit: int = 150) -> str:
    compact = " ".join(str(text or "").split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _connector_payload() -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    try:
        statuses = connector_statuses()
    except Exception as exc:  # pragma: no cover - platform-specific defensive boundary
        return [{"name": "connectors", "available": False, "detail": str(exc), "can_capture": False, "can_read_text": False}]
    for status in statuses:
        payload.append(
            {
                "name": status.name,
                "available": bool(status.available),
                "detail": status.detail,
                "can_capture": bool(status.can_capture),
                "can_read_text": bool(status.can_read_text),
            }
        )
    return payload


def _watch_payload(db_path: Path) -> dict[str, Any]:
    try:
        pids = detect_watch_processes(_process_rows(), current_pid=os.getpid(), db_path=db_path)
    except Exception:  # pragma: no cover - ps/platform-specific defensive boundary
        pids = ()
    return {"running": bool(pids), "process_count": len(pids)}


def _crm_normalize_name(name: str) -> str:
    """Collapse OCR spacing inside a contact name for display and dedupe."""

    return re.sub(r"\s+", "", str(name or ""))


def _crm_noise_name(name: str, *, kind: str = "") -> bool:
    cleaned = _crm_normalize_name(name)
    if not cleaned or cleaned in CRM_NOISE_PHRASES or cleaned in CRM_FILLER_NAMES:
        return True
    if CRM_NOISE_NAME_RE.search(cleaned):
        return True
    # A name made only of counters, currency, punctuation or OCR symbols is
    # an application label rather than a relationship.  Keep one-character
    # Chinese nicknames (for example “妈”) possible by only filtering symbols
    # and numeric labels here.
    if re.fullmatch(r"[+\-\d.,\s元积分（）()．〉>]+", cleaned):
        return True
    if kind == "speaker":
        if len(cleaned) > 16 or len(cleaned) == 1:
            return True
        if any(char in cleaned for char in CRM_SPEAKER_JUNK_CHARS):
            return True
        # UI tokens such as “fan-cool” or “popup-history” start lowercase;
        # real display names essentially never do.
        if cleaned[0].islower() or re.fullmatch(r"[A-Z0-9]{3,}", cleaned):
            return True
        if re.match(r"^[你我他啊]", cleaned) and len(cleaned) >= 3:
            return True
        if re.fullmatch(r"(.)\1+", cleaned):
            return True
    return False


def _crm_content_noise(line: str) -> bool:
    """True when a line is WeChat UI chrome or IME junk, not conversation."""

    compact = " ".join(str(line or "").split()).strip()
    if not compact:
        return True
    if compact in CRM_CONTENT_NOISE_LINES:
        return True
    if CRM_GRAMMAR_LINE_RE.match(compact):
        return True
    return bool(CRM_CONTENT_NOISE_RE.search(compact))


def _crm_dedupe(lines: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for line in lines:
        compact = " ".join(str(line or "").split()).strip()
        if not compact or compact in seen:
            continue
        seen.add(compact)
        result.append(compact)
    return result


def _crm_summary(text: str | None, *, contact_name: str, source_chat: str, speaker: bool) -> str:
    """Distil OCR text into a short conversation summary for a CRM event."""

    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    speaker_lines: list[str] = []
    if speaker and is_group_chat_name(source_chat):
        speaker_lines = speaker_message_map(lines, chat_name=source_chat).get(contact_name, [])
    candidates = speaker_lines or important_content_lines(lines, chat_name=source_chat, limit=8)
    # For direct chats the contact name is normally the window title and is
    # already removed by the parser.  For group chats, prefer lines carrying
    # the speaker name when speaker boundary detection was incomplete.
    if speaker and not speaker_lines:
        focused = [line for line in candidates if contact_name in line]
        if focused:
            candidates = focused + [line for line in candidates if line not in focused]
    candidates = _crm_dedupe([line for line in candidates if not _crm_content_noise(line)])
    if not candidates:
        return "仅识别到联系人，未提取到有效对话内容"
    return "；".join(_preview(line, 180) for line in candidates[:3])


def _crm_parse_age(value: str | None, *, now: datetime) -> int | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=now.tzinfo)
        return max(0, (now - parsed.astimezone(now.tzinfo)).days)
    except (TypeError, ValueError, OverflowError):
        return None


def _crm_signal_rows(conn: sqlite3.Connection) -> dict[int, list[dict[str, str]]]:
    by_capture: dict[int, list[dict[str, str]]] = defaultdict(list)
    if not _table_exists(conn, "capture_signals"):
        return by_capture
    rows = conn.execute(
        "select capture_id, kind, phrase from capture_signals order by capture_id, id"
    ).fetchall()
    for row in rows:
        by_capture[int(row["capture_id"])].append(
            {"kind": str(row["kind"] or ""), "phrase": str(row["phrase"] or "")}
        )
    return by_capture


# Fields the dashboard is allowed to edit on a contact.  Everything else in
# contact_enrichments (company/role/context from Obsidian imports, etc.) is
# preserved untouched by the merge in save_contact_meta.
CONTACT_META_FIELDS = ("category", "tags", "notes")


def _crm_enrichment_map(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    if not _table_exists(conn, "contact_enrichments"):
        return {}
    rows = conn.execute("select person_name, fields_json from contact_enrichments").fetchall()
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        try:
            fields = json.loads(row["fields_json"] or "{}")
        except (TypeError, ValueError):
            continue
        if isinstance(fields, dict):
            result[_crm_normalize_name(row["person_name"])] = {
                str(key): str(value) for key, value in fields.items() if value
            }
    return result


def save_contact_meta(
    db_path: Path | str,
    *,
    person_name: str,
    updates: dict[str, str],
) -> dict[str, Any]:
    """Persist category/tags/notes for a contact, preserving other fields.

    This is the dashboard's single write path.  It merges the three editable
    fields into any existing enrichment record instead of replacing it, so
    company/role/context imported from other sources are not lost.
    """

    db = Path(db_path).expanduser().resolve(strict=False)
    name = " ".join(str(person_name or "").split()).strip()
    if not name or len(name) > 100:
        raise ValueError("person_name is required")
    if not db.is_file():
        raise FileNotFoundError(f"database not found: {db}")
    with closing(_read_connection(db)) as conn:
        people_names = (
            [str(row["name"]) for row in conn.execute("select name from people").fetchall()]
            if _table_exists(conn, "people")
            else []
        )
        rows = (
            conn.execute("select person_name, fields_json from contact_enrichments").fetchall()
            if _table_exists(conn, "contact_enrichments")
            else []
        )
    # The CRM view normalizes OCR spacing in display names; write the metadata
    # back onto the real people row when exactly one normalized match exists.
    if name not in people_names:
        normalized = _crm_normalize_name(name)
        matches = [candidate for candidate in people_names if _crm_normalize_name(candidate) == normalized]
        if len(matches) == 1:
            name = matches[0]
    existing: dict[str, str] = {}
    for row in rows:
        if str(row["person_name"]) == name:
            try:
                payload = json.loads(row["fields_json"] or "{}")
            except (TypeError, ValueError):
                payload = {}
            if isinstance(payload, dict):
                existing = {str(key): str(value) for key, value in payload.items() if value}
            break
    merged = dict(existing)
    for key in CONTACT_META_FIELDS:
        raw = str(updates.get(key) or "").strip()
        value = raw if key == "notes" else " ".join(raw.split())
        value = value[:500]
        if value:
            merged[key] = value
        else:
            merged.pop(key, None)
    if merged:
        record = record_contact_enrichment(db, person_name=name, fields=merged, source="dashboard")
        return {"person_name": record.person_name, "fields": record.fields, "saved": True}
    if existing:
        with connect(db) as conn:
            conn.execute("delete from contact_enrichments where person_name = ?", (name,))
            conn.commit()
    return {"person_name": name, "fields": {}, "saved": True}


def _outreach_payload(db: Path, *, status: str | None = None) -> list[dict[str, Any]]:
    """Read outreach drafts through the read-only connection."""

    if not db.is_file():
        return []
    with closing(_read_connection(db)) as conn:
        if not _table_exists(conn, "outreach_drafts"):
            return []
        query = (
            "select id, person_name, campaign, topic, draft_text, send_mode, status, note, "
            "created_at, updated_at from outreach_drafts"
        )
        params: list[Any] = []
        if status:
            query += " where status = ?"
            params.append(status)
        query += " order by updated_at desc, id desc limit 500"
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def _crm_capture_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    if not _table_exists(conn, "captures"):
        return []
    return conn.execute(
        """
        select c.id, c.captured_at, c.source, c.image_path,
               p.name as chat_name,
               coalesce(c.corrected_text, c.clean_text) as clean_text
        from captures c
        join people p on p.id = c.person_id
        order by c.captured_at desc, c.id desc
        """
    ).fetchall()


def _crm_suggestion_payload(suggestion: Any) -> dict[str, Any]:
    return {
        "action": str(suggestion.action),
        "why": str(suggestion.why),
        "draft": str(suggestion.draft),
        "score": int(suggestion.score),
        "evidence_captured_at": suggestion.evidence_captured_at,
    }


def _crm_merge_contacts(
    contacts: list[dict[str, Any]], *, timeline_limit: int
) -> list[dict[str, Any]]:
    """Merge direct-chat and group-speaker entries that share one name.

    OCR spacing variants (“寧 NING” / “寧NING”) and the same person appearing
    both as a chat title and as a group speaker should surface as a single
    CRM contact with one combined timeline.
    """

    merged: dict[str, dict[str, Any]] = {}
    for contact in contacts:
        key = _crm_normalize_name(contact["name"]) or str(contact["name"])
        existing = merged.get(key)
        if existing is None:
            contact["name"] = key
            contact["kinds"] = {contact["kind"]}
            merged[key] = contact
            continue
        existing["kinds"].add(contact["kind"])
        if contact["kind"] == "direct":
            existing["kind"] = "direct"
        seen = {int(event["capture_id"]) for event in existing["timeline"]}
        for event in contact["timeline"]:
            if int(event["capture_id"]) not in seen:
                existing["timeline"].append(event)
                seen.add(int(event["capture_id"]))
        existing["timeline"].sort(
            key=lambda item: (str(item["captured_at"] or ""), int(item["capture_id"])),
            reverse=True,
        )
        del existing["timeline"][timeline_limit:]
        for field in ("signals", "organizations", "identity_hints", "source_chats"):
            combined = list(existing[field])
            for value in contact[field]:
                if value not in combined:
                    combined.append(value)
            existing[field] = combined
        if int(contact["next_action"].get("score", 0)) > int(existing["next_action"].get("score", 0)):
            existing["next_action"] = contact["next_action"]
    result = list(merged.values())
    for contact in result:
        kinds = contact.pop("kinds")
        if kinds == {"direct", "speaker"}:
            contact["kind_label"] = "直接联系人 · 群聊发言人"
        elif "direct" in kinds:
            contact["kind_label"] = "直接联系人"
        else:
            contact["kind_label"] = "群聊联系人"
        contact["interaction_count"] = len(contact["timeline"])
        contact["last_interaction_at"] = contact["timeline"][0]["captured_at"]
        contact["summary"] = contact["timeline"][0]["summary"]
        contact["source_chats"] = sorted(contact["source_chats"])
    return result


def build_crm_view(
    db_path: Path | str,
    *,
    captures_dir: Path | str | None = None,
    limit: int = 100,
    timeline_limit: int = 12,
) -> dict[str, Any]:
    """Build the relationship-first view used by the dashboard.

    This is intentionally a derived read model.  It keeps evidence and OCR
    observations in SQLite, while returning only contact-level summaries and
    time-ordered interactions to the UI.  Nothing in this function writes to
    the database or exposes the raw OCR stream.
    """

    db = Path(db_path).expanduser().resolve(strict=False)
    capture_root = resolve_captures_dir(db, captures_dir)
    payload: dict[str, Any] = {
        "generated_at": _now_iso(),
        "mode": "crm",
        "db": {"path": str(db), "exists": db.is_file()},
        "captures_dir": str(capture_root),
        "watch": _watch_payload(db),
        "stats": {"contacts": 0, "interactions": 0, "active_7d": 0, "followups": 0, "captures": 0},
        "notices": [],
        "contacts": [],
    }
    if not db.is_file():
        return payload

    try:
        profiles = build_profiles(db)
        with closing(_read_connection(db)) as conn:
            capture_rows = _crm_capture_rows(conn)
            signal_by_capture = _crm_signal_rows(conn)
            enrichment_map = _crm_enrichment_map(conn)
    except (OSError, sqlite3.DatabaseError, ValueError):
        return payload

    payload["stats"]["captures"] = len(capture_rows)

    # Suggestions are useful CRM context, but a malformed OCR record must not
    # make the dashboard unavailable.  The evidence timeline remains useful
    # even when the optional scoring layer cannot be built.
    suggestions: dict[str, Any] = {}
    try:
        suggestions = {
            item.person_name: item
            for item in build_suggestions(db, as_of=payload["generated_at"], limit=1000, min_score=0)
        }
    except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
        suggestions = {}

    bounded_limit = max(1, min(200, int(limit)))
    bounded_timeline = max(1, min(30, int(timeline_limit)))
    now = datetime.now().astimezone()
    contacts: list[dict[str, Any]] = []

    # Group speakers are only surfaced when they already exist in the local
    # contact list: a direct-chat title or a manual enrichment record.
    known_names = {
        _crm_normalize_name(str(row["chat_name"] or ""))
        for row in capture_rows
        if not is_group_chat_name(str(row["chat_name"] or ""))
    } | set(enrichment_map.keys())

    for profile in profiles:
        if profile.kind not in {"direct", "speaker"} or _crm_noise_name(profile.name, kind=profile.kind):
            continue
        if profile.kind == "speaker" and _crm_normalize_name(profile.name) not in known_names:
            continue
        if profile.kind == "direct":
            rows = [row for row in capture_rows if row["chat_name"] == profile.name]
        else:
            source_chats = set(profile.source_chats)
            rows = [row for row in capture_rows if row["chat_name"] in source_chats]

        timeline: list[dict[str, Any]] = []
        seen_captures: set[int] = set()
        for row in rows:
            capture_id = int(row["id"])
            if capture_id in seen_captures:
                continue
            source_chat = str(row["chat_name"] or profile.name)
            speaker = profile.kind == "speaker"
            if speaker:
                lines = [line.strip() for line in str(row["clean_text"] or "").splitlines() if line.strip()]
                messages = speaker_message_map(lines, chat_name=source_chat).get(profile.name, [])
                # Do not attribute a whole group transcript to every speaker
                # when the OCR parser could not establish a speaker boundary.
                if not messages and profile.name not in str(row["clean_text"] or ""):
                    continue
            summary = _crm_summary(
                row["clean_text"],
                contact_name=profile.name,
                source_chat=source_chat,
                speaker=speaker,
            )
            if not summary:
                continue
            signals = list(signal_by_capture.get(capture_id, ()))
            if speaker:
                speaker_text = "\n".join(
                    speaker_message_map(
                        [line.strip() for line in str(row["clean_text"] or "").splitlines() if line.strip()],
                        chat_name=source_chat,
                    ).get(profile.name, [])
                )
                inferred = extract_signals(speaker_text)
            else:
                inferred = extract_signals(str(row["clean_text"] or ""))
            known_kinds = {item["kind"] for item in signals}
            for signal in inferred:
                if signal.kind not in known_kinds:
                    signals.append({"kind": signal.kind, "phrase": signal.phrase})
                    known_kinds.add(signal.kind)
            image_available = _managed_image_path(row["image_path"], capture_root, db_path=db) is not None
            timeline.append(
                {
                    "capture_id": capture_id,
                    "captured_at": row["captured_at"],
                    "source_chat": source_chat,
                    "source": row["source"],
                    "summary": summary,
                    "signals": signals[:6],
                    "image_available": image_available,
                }
            )
            seen_captures.add(capture_id)

        timeline.sort(key=lambda item: (str(item["captured_at"] or ""), item["capture_id"]), reverse=True)
        if not timeline:
            continue
        timeline = timeline[:bounded_timeline]
        source_chats = sorted({str(item["source_chat"]) for item in timeline if item.get("source_chat")})
        contact_signals: list[dict[str, str]] = []
        for event in timeline:
            for signal in event.get("signals", []):
                if signal not in contact_signals:
                    contact_signals.append(signal)
        suggestion = suggestions.get(profile.name)
        next_action = _crm_suggestion_payload(suggestion) if suggestion else {
            "action": "保持联系",
            "why": "已有互动记录，可按关系节奏继续关注",
            "draft": "",
            "score": 0,
            "evidence_captured_at": None,
        }
        last_interaction = timeline[0]["captured_at"]
        contacts.append(
            {
                "name": profile.name,
                "kind": profile.kind,
                "kind_label": "直接联系人" if profile.kind == "direct" else "群聊联系人",
                "last_interaction_at": last_interaction,
                "interaction_count": len(timeline),
                "source_chats": source_chats,
                "summary": timeline[0]["summary"],
                "signals": contact_signals[:8],
                "organizations": list(profile.organizations[:6]),
                "identity_hints": list(profile.identity_hints[:6]),
                "next_action": next_action,
                "timeline": timeline,
            }
        )

    contacts = _crm_merge_contacts(contacts, timeline_limit=bounded_timeline)
    for contact in contacts:
        fields = enrichment_map.get(_crm_normalize_name(contact["name"]), {})
        contact["category"] = fields.get("category", "")
        contact["tags"] = fields.get("tags", "")
        contact["notes"] = fields.get("notes", "")
    contacts.sort(
        key=lambda item: (str(item.get("last_interaction_at") or ""), str(item.get("name") or "")),
        reverse=True,
    )
    contacts = contacts[:bounded_limit]
    if not contacts and capture_rows:
        payload["notices"].append(
            {
                "kind": "capture_context",
                "message": (
                    f"已采集 {len(capture_rows)} 张截图，但当前记录来自微信会话列表或其他界面，"
                    "没有可用于联系人 CRM 的聊天内容。请在微信中打开具体联系人聊天窗口，"
                    "保持微信在最前台后再运行 watch。"
                ),
            }
        )
    payload["contacts"] = contacts
    payload["stats"] = {
        "contacts": len(contacts),
        "interactions": sum(int(item["interaction_count"]) for item in contacts),
        "active_7d": sum(1 for item in contacts if (_crm_parse_age(item["last_interaction_at"], now=now) or 9999) <= 7),
        "followups": sum(1 for item in contacts if int(item["next_action"].get("score", 0)) >= 45),
        "captures": len(capture_rows),
    }
    return payload


def build_overview(
    db_path: Path | str,
    *,
    captures_dir: Path | str | None = None,
    log_file: Path | str | None = None,
    include_connectors: bool = True,
) -> dict[str, Any]:
    """Build the dashboard summary without creating or modifying local data."""

    db = Path(db_path).expanduser().resolve(strict=False)
    capture_root = resolve_captures_dir(db, captures_dir)
    log = Path(log_file or db.parent / "watch.log").expanduser().resolve(strict=False)
    counts = {
        "contacts": 0,
        "captures": 0,
        "signals": 0,
        "observations": 0,
        "pending_low_confidence": 0,
        "reviewed_observations": 0,
        "pending_message_candidates": 0,
        "pending_participant_mentions": 0,
        "pending_relation_events": 0,
    }
    latest: dict[str, Any] | None = None
    buckets: list[dict[str, Any]] = []
    average_confidence: float | None = None
    known_confidence = 0
    sources: list[dict[str, Any]] = []
    schema_version: int | None = None

    if db.is_file():
        try:
            with closing(_read_connection(db)) as conn:
                counts["contacts"] = _count(conn, "people")
                counts["captures"] = _count(conn, "captures")
                counts["observations"] = _count(conn, "ocr_observations")
                counts["reviewed_observations"] = int(
                    conn.execute(
                        "select count(*) from ocr_reviews where status in ('accepted', 'rejected', 'corrected')"
                    ).fetchone()[0]
                ) if _table_exists(conn, "ocr_reviews") else 0
                if _table_exists(conn, "ocr_observations"):
                    counts["pending_low_confidence"] = int(
                        conn.execute(
                            """
                            select count(*)
                            from ocr_observations o
                            left join ocr_reviews r on r.observation_id = o.id
                            where r.id is null
                              and (o.confidence is null or o.confidence <= ?)
                            """,
                            (LOW_CONFIDENCE_THRESHOLD,),
                        ).fetchone()[0]
                    )
                for table, key in (
                    ("message_candidates", "pending_message_candidates"),
                    ("participant_mentions", "pending_participant_mentions"),
                    ("relation_events", "pending_relation_events"),
                ):
                    if _table_exists(conn, table):
                        counts[key] = int(
                            conn.execute(
                                f"select count(*) from {table} where status = 'candidate'"
                            ).fetchone()[0]
                        )
                counts["signals"] = _current_signal_count(conn)
                buckets, average_confidence, known_confidence = _confidence_buckets(conn)
                sources = _source_counts(conn)
                if _table_exists(conn, "schema_migrations"):
                    row = conn.execute("select coalesce(max(version), 0) from schema_migrations").fetchone()
                    schema_version = int(row[0]) if row else 0
                if _table_exists(conn, "captures"):
                    row = conn.execute(
                        """
                        select c.id, c.captured_at, p.name as contact_name, c.source, c.image_path,
                               c.capture_stability, c.capture_frames
                        from captures c join people p on p.id = c.person_id
                        order by c.captured_at desc, c.id desc limit 1
                        """
                    ).fetchone()
                    if row:
                        image = _managed_image_path(row["image_path"], capture_root, db_path=db)
                        latest = {
                            "id": int(row["id"]),
                            "captured_at": row["captured_at"],
                            "contact_name": row["contact_name"],
                            "source": row["source"],
                            "capture_frames": int(row["capture_frames"] or 1),
                            "capture_stability": _json_float(row["capture_stability"]),
                            "image_available": image is not None,
                        }
        except (OSError, sqlite3.DatabaseError) as exc:
            return {
                "generated_at": _now_iso(),
                "db": {"path": str(db), "exists": True, "schema_version": schema_version, "error": str(exc)},
                "captures_dir": str(capture_root),
                "watch": _watch_payload(db),
                "counts": counts,
                "quality": {"confidence_buckets": buckets, "average_confidence": average_confidence, "known_confidence": known_confidence, "source_counts": sources},
                "latest": latest,
                "screenshots": {
                    "count": sum(_count_screenshots(root) for root in capture_storage_roots(db, captures_dir)),
                    "dir": str(capture_root),
                },
                "log": {"path": str(log), "exists": log.is_file(), "line_count": _line_count(log), "last_line": _tail_line(log)},
                "connectors": _connector_payload() if include_connectors else [],
            }

    return {
        "generated_at": _now_iso(),
        "db": {"path": str(db), "exists": db.is_file(), "schema_version": schema_version},
        "captures_dir": str(capture_root),
        "watch": _watch_payload(db),
        "counts": counts,
        "quality": {
            "confidence_buckets": buckets,
            "average_confidence": average_confidence,
            "known_confidence": known_confidence,
            "source_counts": sources,
            "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
        },
        "latest": latest,
        "screenshots": {
            "count": sum(_count_screenshots(root) for root in capture_storage_roots(db, captures_dir)),
            "dir": str(capture_root),
        },
        "log": {"path": str(log), "exists": log.is_file(), "line_count": _line_count(log), "last_line": _tail_line(log)},
        "connectors": _connector_payload() if include_connectors else [],
    }


def list_captures(
    db_path: Path | str,
    *,
    captures_dir: Path | str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return recent capture metadata for the timeline (never image bytes)."""

    db = Path(db_path).expanduser().resolve(strict=False)
    capture_root = resolve_captures_dir(db, captures_dir)
    if not db.is_file():
        return []
    bounded_limit = max(1, min(100, int(limit)))
    with closing(_read_connection(db)) as conn:
        if not _table_exists(conn, "captures"):
            return []
        rows = conn.execute(
            """
            select c.id, p.name as contact_name, c.captured_at, c.source, c.image_path,
                   c.capture_frames, c.capture_stability,
                   coalesce(c.corrected_text, c.clean_text) as clean_text,
                   (select count(*) from ocr_observations o where o.capture_id = c.id) as observation_count,
                   (select count(*) from ocr_observations o where o.capture_id = c.id
                     and (o.confidence is null or o.confidence <= ?)
                   ) as low_confidence_count,
                   (select count(*) from capture_signals s where s.capture_id = c.id) as signal_count,
                   r.connector as perception_connector, r.backend as perception_backend,
                   r.status as perception_status
            from captures c
            join people p on p.id = c.person_id
            left join perception_runs r on r.capture_id = c.id
            order by c.captured_at desc, c.id desc limit ?
            """,
            (LOW_CONFIDENCE_THRESHOLD, bounded_limit),
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "contact_name": row["contact_name"],
            "captured_at": row["captured_at"],
            "source": row["source"],
            "capture_frames": int(row["capture_frames"] or 1),
            "capture_stability": _json_float(row["capture_stability"]),
            "preview": _preview(row["clean_text"]),
            "observation_count": int(row["observation_count"] or 0),
            "low_confidence_count": int(row["low_confidence_count"] or 0),
            "signal_count": int(row["signal_count"] or 0),
            "perception_connector": row["perception_connector"],
            "perception_backend": row["perception_backend"],
            "perception_status": row["perception_status"],
            "image_available": _managed_image_path(row["image_path"], capture_root, db_path=db) is not None,
        }
        for row in rows
    ]


def capture_detail(
    db_path: Path | str,
    capture_id: int,
    *,
    captures_dir: Path | str | None = None,
) -> dict[str, Any] | None:
    """Return one capture and its structured OCR observations."""

    db = Path(db_path).expanduser().resolve(strict=False)
    capture_root = resolve_captures_dir(db, captures_dir)
    if not db.is_file() or capture_id < 1:
        return None
    with closing(_read_connection(db)) as conn:
        if not _table_exists(conn, "captures"):
            return None
        capture = conn.execute(
            """
            select c.id, p.name as contact_name, c.captured_at, c.source, c.image_path,
                   c.raw_text, c.clean_text, c.corrected_text, c.capture_frames, c.capture_stability,
                   r.connector as perception_connector, r.backend as perception_backend,
                   r.status as perception_status, r.frame_count as perception_frame_count,
                   r.stability as perception_stability, r.error as perception_error
            from captures c
            join people p on p.id = c.person_id
            left join perception_runs r on r.capture_id = c.id
            where c.id = ?
            """,
            (capture_id,),
        ).fetchone()
        if capture is None:
            return None
        observations: list[dict[str, Any]] = []
        if _table_exists(conn, "ocr_observations"):
            rows = conn.execute(
                """
                select o.id, o.sequence, o.text, o.confidence, o.bbox_x, o.bbox_y,
                       o.bbox_width, o.bbox_height, o.source, o.speaker_candidate,
                       o.speaker_confidence, o.role, o.subrole, o.node_path, o.parent_path,
                       o.depth, coalesce(r.status, 'pending') as review_status,
                       r.corrected_text, r.corrected_speaker
                from ocr_observations o
                left join ocr_reviews r on r.observation_id = o.id
                where o.capture_id = ? order by o.sequence, o.id
                """,
                (capture_id,),
            ).fetchall()
            for row in rows:
                bbox_values = (row["bbox_x"], row["bbox_y"], row["bbox_width"], row["bbox_height"])
                observations.append(
                    {
                        "id": int(row["id"]),
                        "sequence": int(row["sequence"]),
                        "text": row["text"],
                        "confidence": _json_float(row["confidence"]),
                        "bbox": [_json_float(value) for value in bbox_values] if all(value is not None for value in bbox_values) else None,
                        "source": row["source"],
                        "speaker_candidate": row["speaker_candidate"],
                        "speaker_confidence": _json_float(row["speaker_confidence"]),
                        "role": row["role"],
                        "subrole": row["subrole"],
                        "node_path": row["node_path"],
                        "parent_path": row["parent_path"],
                        "depth": row["depth"],
                        "review_status": row["review_status"],
                        "corrected_text": row["corrected_text"],
                        "corrected_speaker": row["corrected_speaker"],
                    }
                )
        signals: list[dict[str, str]] = []
        if _table_exists(conn, "capture_signals"):
            signals = [
                {"kind": row["kind"], "phrase": row["phrase"]}
                for row in conn.execute(
                    "select kind, phrase from capture_signals where capture_id = ? order by id",
                    (capture_id,),
                ).fetchall()
            ]
    image = _managed_image_path(capture["image_path"], capture_root, db_path=db)
    return {
        "id": int(capture["id"]),
        "contact_name": capture["contact_name"],
        "captured_at": capture["captured_at"],
        "source": capture["source"],
        "capture_frames": int(capture["capture_frames"] or 1),
        "capture_stability": _json_float(capture["capture_stability"]),
        "image_available": image is not None,
        "raw_text": capture["raw_text"],
        "clean_text": capture["clean_text"],
        "corrected_text": capture["corrected_text"],
        "effective_text": capture["corrected_text"] or capture["clean_text"],
        "perception": {
            "connector": capture["perception_connector"],
            "backend": capture["perception_backend"],
            "status": capture["perception_status"],
            "frame_count": capture["perception_frame_count"],
            "stability": _json_float(capture["perception_stability"]),
            "error": capture["perception_error"],
        },
        "signals": signals,
        "observations": observations,
    }


def _capture_image(db_path: Path, capture_id: int, captures_dir: Path) -> Path | None:
    if not db_path.is_file() or capture_id < 1:
        return None
    with closing(_read_connection(db_path)) as conn:
        if not _table_exists(conn, "captures"):
            return None
        row = conn.execute("select image_path from captures where id = ?", (capture_id,)).fetchone()
    return _managed_image_path(row["image_path"] if row else None, captures_dir, db_path=db_path)


class DashboardHTTPServer(ThreadingHTTPServer):
    """HTTP server carrying immutable dashboard configuration."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, *, db_path: Path, captures_dir: Path, log_file: Path):
        super().__init__(address, handler)
        self.db_path = db_path
        self.captures_dir = captures_dir
        self.log_file = log_file


class IPv6DashboardHTTPServer(DashboardHTTPServer):
    address_family = socket.AF_INET6


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardHTTPServer

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/":
                self._send_bytes(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/api/overview":
                overview = build_overview(
                    self.server.db_path,
                    captures_dir=self.server.captures_dir,
                    log_file=self.server.log_file,
                )
                self._send_json(overview)
                return
            if path == "/api/crm":
                query = parse_qs(parsed.query)
                limit = _query_limit(query.get("limit", ["100"])[0])
                self._send_json(
                    build_crm_view(
                        self.server.db_path,
                        captures_dir=self.server.captures_dir,
                        limit=limit,
                    )
                )
                return
            if path == "/api/outreach":
                query = parse_qs(parsed.query)
                status = query.get("status", [""])[0].strip() or None
                self._send_json({"drafts": _outreach_payload(self.server.db_path, status=status)})
                return
            if path == "/api/captures":
                query = parse_qs(parsed.query)
                limit = _query_limit(query.get("limit", ["50"])[0])
                self._send_json(
                    {"captures": list_captures(self.server.db_path, captures_dir=self.server.captures_dir, limit=limit)}
                )
                return
            if path.startswith("/api/captures/"):
                capture_id = _path_id(path, "/api/captures/")
                if capture_id is None:
                    self._send_error_json(404, "capture not found")
                    return
                detail = capture_detail(self.server.db_path, capture_id, captures_dir=self.server.captures_dir)
                if detail is None:
                    self._send_error_json(404, "capture not found")
                else:
                    self._send_json(detail)
                return
            if path.startswith("/media/"):
                capture_id = _path_id(path, "/media/")
                if capture_id is None:
                    self._send_error_json(404, "image not found")
                    return
                image = _capture_image(self.server.db_path, capture_id, self.server.captures_dir)
                if image is None:
                    self._send_error_json(404, "image not found")
                else:
                    content_type = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
                    self._send_bytes(image.read_bytes(), content_type, cache_control="no-cache")
                return
            self._send_error_json(404, "not found")
        except (OSError, sqlite3.DatabaseError, ValueError) as exc:
            self._send_error_json(500, str(exc))

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        """The dashboard's write routes: contact profile and outreach drafts.

        Both are local user clicks on the loopback panel, which is the
        confirmation; the MCP-facing domain functions still receive explicit
        confirmation fields so the audit semantics stay identical.
        """

        parsed = urlparse(self.path)
        if parsed.path not in {"/api/enrichment", "/api/outreach"}:
            self._send_error_json(404, "not found")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if not 0 < length <= 65536:
            self._send_error_json(400, "invalid request body")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self._send_error_json(400, "invalid JSON body")
            return
        if not isinstance(payload, dict):
            self._send_error_json(400, "invalid JSON body")
            return
        try:
            if parsed.path == "/api/enrichment":
                result = save_contact_meta(
                    self.server.db_path,
                    person_name=str(payload.get("person_name") or ""),
                    updates={key: str(payload.get(key) or "") for key in CONTACT_META_FIELDS},
                )
            else:
                draft = update_outreach_draft(
                    self.server.db_path,
                    draft_id=int(payload.get("draft_id") or 0),
                    action=str(payload.get("action") or ""),
                    draft_text=payload.get("draft_text"),
                    note=payload.get("note"),
                    confirmed=True,
                    confirmation_text=UPDATE_CONFIRMATION_TEXT,
                )
                result = {"draft": outreach_to_dict(draft)}
        except (ValueError, FileNotFoundError) as exc:
            self._send_error_json(400, str(exc))
            return
        except (OSError, sqlite3.DatabaseError) as exc:
            self._send_error_json(500, str(exc))
            return
        self._send_json(result)

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status=status)

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def _send_bytes(
        self,
        body: bytes,
        content_type: str,
        *,
        status: int = 200,
        cache_control: str = "no-store",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        # Keep the terminal useful while still allowing a caller to see errors.
        sys.stderr.write(f"wsa-ui: {format % args}\n")


def _query_limit(value: str) -> int:
    try:
        return max(1, min(100, int(value)))
    except (TypeError, ValueError):
        return 50


def _path_id(path: str, prefix: str) -> int | None:
    raw = path.removeprefix(prefix).strip("/")
    if not raw.isdigit():
        return None
    value = int(raw)
    return value if value > 0 else None


def serve_dashboard(
    db_path: Path | str,
    *,
    captures_dir: Path | str | None = None,
    log_file: Path | str | None = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
) -> int:
    """Run the loopback-only dashboard until Ctrl-C."""

    if host not in LOCAL_HOSTS:
        raise ValueError("wsa ui only binds to localhost (127.0.0.1, localhost, or ::1)")
    if not 1 <= int(port) <= 65535:
        raise ValueError("port must be between 1 and 65535")
    db = Path(db_path).expanduser().resolve(strict=False)
    capture_root = resolve_captures_dir(db, captures_dir)
    log = Path(log_file or db.parent / "watch.log").expanduser().resolve(strict=False)
    server_class = IPv6DashboardHTTPServer if host == "::1" else DashboardHTTPServer
    server = server_class((host, int(port)), DashboardHandler, db_path=db, captures_dir=capture_root, log_file=log)
    host_for_url = f"[{host}]" if ":" in host else host
    url = f"http://{host_for_url}:{server.server_port}/"
    print(f"WSA dashboard: {url}")
    print("只读本地面板；按 Ctrl-C 停止。")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:  # pragma: no cover - browser availability is platform-specific
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWSA dashboard stopped.", file=sys.stderr)
    finally:
        server.server_close()
    return 0


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>WSA 关系面板</title>
  <style>
    :root { color-scheme: dark; --bg:#0d1117; --panel:#151c25; --panel-2:#1b2531; --line:#2a3746; --text:#e8eef5; --muted:#95a6b8; --accent:#67d5bd; --blue:#7bb6ff; --warn:#f3bd64; --bad:#ff8d8d; }
    * { box-sizing:border-box; }
    body { margin:0; background:radial-gradient(circle at 10% 0%,#1b3040 0,#0d1117 38%); color:var(--text); font:14px/1.55 -apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC",sans-serif; }
    main { max-width:1280px; margin:0 auto; padding:28px 22px 48px; }
    header { display:flex; justify-content:space-between; gap:18px; align-items:flex-end; margin-bottom:22px; flex-wrap:wrap; }
    h1,h2,h3,p { margin:0; } h1 { letter-spacing:-.03em; font-size:28px; } h2 { font-size:16px; }
    .eyebrow { color:var(--accent); text-transform:uppercase; font-size:11px; letter-spacing:.15em; font-weight:700; margin-bottom:5px; }
    .muted { color:var(--muted); } .small { font-size:12px; } .right { text-align:right; }
    .grid { display:grid; gap:14px; } .cards { grid-template-columns:repeat(4,minmax(140px,1fr)); margin-bottom:14px; }
    .panel,.card { background:linear-gradient(145deg,rgba(29,41,53,.94),rgba(17,24,32,.96)); border:1px solid var(--line); border-radius:15px; box-shadow:0 12px 35px rgba(0,0,0,.16); }
    .panel { padding:18px; } .card { padding:15px; min-height:88px; }
    .label { color:var(--muted); font-size:12px; } .value { font-size:27px; line-height:1.15; font-weight:700; margin-top:9px; }
    .value.good { color:var(--accent); } .value.warn { color:var(--warn); }
    .toolbar { display:flex; gap:12px; align-items:center; }
    button { border:1px solid var(--line); border-radius:9px; color:var(--text); background:var(--panel-2); padding:7px 11px; cursor:pointer; font:inherit; }
    button:hover { border-color:var(--accent); }
    .status-dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--warn); margin-right:7px; } .status-dot.on { background:var(--accent); box-shadow:0 0 10px rgba(103,213,189,.7); }
    .pill { display:inline-flex; align-items:center; gap:5px; border:1px solid var(--line); border-radius:99px; padding:2px 8px; font-size:11px; color:var(--muted); white-space:nowrap; }
    .pill.good { color:var(--accent); border-color:rgba(103,213,189,.4); } .pill.blue { color:var(--blue); border-color:rgba(123,182,255,.45); }
    .layout { grid-template-columns:minmax(300px,360px) minmax(0,1fr); align-items:start; }
    .list-head { display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom:12px; }
    #contactSearch { flex:1; max-width:190px; background:#0e151c; border:1px solid var(--line); border-radius:9px; color:var(--text); padding:7px 10px; font:inherit; }
    #contactSearch:focus { outline:none; border-color:var(--accent); }
    .contact-list { display:grid; gap:8px; max-height:72vh; overflow:auto; }
    .contact-item { display:block; width:100%; text-align:left; border:1px solid var(--line); border-radius:11px; background:rgba(255,255,255,.02); padding:10px 12px; cursor:pointer; color:var(--text); font:inherit; }
    .contact-item:hover { border-color:rgba(103,213,189,.5); }
    .contact-item.selected { border-color:var(--accent); background:rgba(103,213,189,.08); }
    .contact-top { display:flex; justify-content:space-between; align-items:center; gap:8px; }
    .contact-name { font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .contact-snippet { color:var(--muted); font-size:12px; margin-top:5px; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
    .detail-head { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; flex-wrap:wrap; }
    .meta-row { display:flex; flex-wrap:wrap; gap:7px; margin-top:10px; }
    .next-action { border-left:3px solid var(--blue); background:rgba(123,182,255,.08); padding:10px 12px; border-radius:8px; margin-top:14px; }
    .next-action .draft { color:var(--muted); font-size:12px; margin-top:6px; white-space:pre-wrap; }
    .notice { border-left:3px solid var(--warn); background:rgba(243,189,100,.1); color:#ead6ac; padding:10px 12px; border-radius:8px; margin-bottom:14px; }
    .timeline { display:grid; gap:10px; margin-top:14px; }
    .event { border-left:3px solid var(--accent); background:rgba(255,255,255,.035); border-radius:8px; padding:10px 12px; }
    .event-meta { display:flex; flex-wrap:wrap; gap:7px; align-items:center; color:var(--muted); font-size:12px; }
    .event-text { margin-top:6px; white-space:pre-wrap; overflow-wrap:anywhere; }
    .event-signals { display:flex; flex-wrap:wrap; gap:6px; margin-top:7px; }
    .shot { display:block; margin-top:9px; max-width:100%; max-height:420px; border-radius:10px; border:1px solid var(--line); }
    .empty-detail { display:grid; place-items:center; min-height:220px; color:var(--muted); border:1px dashed var(--line); border-radius:10px; text-align:center; padding:22px; }
    .section-label { color:var(--muted); font-size:12px; margin-top:14px; }
    .meta-form { display:grid; gap:9px; margin-top:8px; max-width:520px; }
    .meta-form label { color:var(--muted); font-size:12px; display:grid; gap:4px; }
    .meta-form input, .meta-form textarea { width:100%; background:#0e151c; border:1px solid var(--line); border-radius:9px; color:var(--text); padding:7px 10px; font:inherit; }
    .meta-form input:focus, .meta-form textarea:focus { outline:none; border-color:var(--accent); }
    .meta-form textarea { min-height:74px; resize:vertical; }
    .meta-save { display:flex; gap:10px; align-items:center; }
    .save-status { font-size:12px; color:var(--accent); }
    .pill.warn { color:var(--warn); border-color:rgba(243,189,100,.45); }
    .draft-list { display:grid; gap:10px; margin-top:12px; }
    .draft { border:1px solid var(--line); border-radius:10px; padding:12px; background:rgba(255,255,255,.02); }
    .draft-head { display:flex; flex-wrap:wrap; gap:7px; align-items:center; }
    .draft-name { font-weight:600; cursor:pointer; }
    .draft-name:hover { color:var(--accent); }
    .draft-text { margin-top:8px; white-space:pre-wrap; overflow-wrap:anywhere; }
    .draft-actions { display:flex; gap:8px; margin-top:10px; }
    .draft-actions button { font-size:12px; padding:5px 10px; }
    .error { color:var(--bad); } .footer { color:var(--muted); margin-top:20px; font-size:12px; }
    @media (max-width:980px) { .layout { grid-template-columns:1fr; } .cards { grid-template-columns:repeat(2,1fr); } .right { text-align:left; } }
  </style>
</head>
<body>
<main>
  <header>
    <div><div class="eyebrow">Wechat Social Assistant · local CRM</div><h1>关系面板</h1><p class="muted">提取到哪些联系人，以及围绕每个联系人在什么时间谈了什么（本地 OCR 提炼）。</p></div>
    <div class="right"><div id="watchStatus" class="pill"><span class="status-dot"></span>读取中</div><p id="updatedAt" class="muted small" style="margin-top:7px">—</p><div class="toolbar" style="justify-content:flex-end;margin-top:9px"><button id="refresh">刷新</button></div></div>
  </header>
  <section class="grid cards">
    <div class="card"><div class="label">已提取联系人</div><div id="statContacts" class="value">—</div></div>
    <div class="card"><div class="label">谈话记录</div><div id="statInteractions" class="value">—</div></div>
    <div class="card"><div class="label">近 7 天活跃</div><div id="statActive" class="value good">—</div></div>
    <div class="card"><div class="label">建议跟进</div><div id="statFollowups" class="value warn">—</div></div>
  </section>
  <div id="crmNotice" class="notice" style="display:none"></div>
  <section class="grid layout">
    <section class="panel">
      <div class="list-head"><h2>联系人</h2><input id="contactSearch" type="search" placeholder="搜索姓名 / 内容…" /></div>
      <div id="contactList" class="contact-list"><p class="muted">读取中…</p></div>
    </section>
    <section class="panel" id="detailPanel"><div class="empty-detail">从左侧选择一个联系人，查看谈话时间线。</div></section>
  </section>
  <section class="panel" id="outreachPanel" style="margin-top:14px">
    <h2>外联草稿箱</h2>
    <p class="muted small" style="margin-top:4px">宿主 Agent 生成的个性化草稿。批准后由你手动发送；标记 computer_use 且已批准的草稿，可由具备电脑操作能力的宿主代为输入微信。WSA 永远不自动发送。</p>
    <div id="draftList" class="draft-list"><p class="muted">读取中…</p></div>
  </section>
  <p class="footer">证据与谈话记录只读；本页仅可维护联系人档案（分类 / 标签 / 备注），写入本地数据库。采集、删除等操作仍通过 CLI/MCP 的显式确认完成。内容为本地 OCR 提炼，可能不完整或存在个别误识别。</p>
</main>
<script>
const $ = (id) => document.getElementById(id);
const esc = (value) => value == null ? '' : String(value);
const fmtTime = (value) => { if (!value) return '—'; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', {hour12:false}); };
let crmData = null;
let selectedName = null;
let searchText = '';
let editingMeta = false;
function pill(text, kind='') { const span=document.createElement('span'); span.className=`pill ${kind}`; span.textContent=text; return span; }
function contactText(contact) { return [contact.name, contact.summary, contact.category, contact.tags, contact.notes, ...(contact.source_chats||[]), ...(contact.timeline||[]).map((event)=>event.summary)].join('\n'); }
function renderStats() {
  const stats=(crmData&&crmData.stats)||{};
  $('statContacts').textContent=esc(stats.contacts ?? 0);
  $('statInteractions').textContent=esc(stats.interactions ?? 0);
  $('statActive').textContent=esc(stats.active_7d ?? 0);
  $('statFollowups').textContent=esc(stats.followups ?? 0);
}
function renderNotice() {
  const box=$('crmNotice'); box.replaceChildren();
  const notices=(crmData&&crmData.notices)||[];
  if(!notices.length){ box.style.display='none'; return; }
  box.style.display='block';
  notices.forEach((notice)=>{ const line=document.createElement('div'); line.textContent=notice.message||''; box.appendChild(line); });
}
function renderList() {
  const list=$('contactList'); list.replaceChildren();
  const contacts=((crmData&&crmData.contacts)||[]).filter((contact)=>!searchText || contactText(contact).includes(searchText));
  if(!contacts.length){ const empty=document.createElement('p'); empty.className='muted'; empty.textContent=searchText?'没有匹配的联系人。':'尚未提取到联系人。先运行 ./start.sh capture 或启动 watch 采集微信窗口。'; list.appendChild(empty); return; }
  contacts.forEach((contact)=>{
    const item=document.createElement('button'); item.type='button'; item.className='contact-item'+(contact.name===selectedName?' selected':'');
    const top=document.createElement('div'); top.className='contact-top';
    const name=document.createElement('span'); name.className='contact-name'; name.textContent=esc(contact.name);
    top.append(name, pill(`${contact.interaction_count} 次`, 'good'));
    const meta=document.createElement('div'); meta.className='meta-row'; meta.style.marginTop='6px';
    meta.appendChild(pill(contact.kind_label||'', 'blue'));
    (contact.source_chats||[]).filter((chat)=>chat!==contact.name).forEach((chat)=>meta.appendChild(pill(`来自群聊：${chat}`, 'blue')));
    if(contact.category) meta.appendChild(pill(contact.category, 'good'));
    (String(contact.tags||'').split(/[,，]/).map((tag)=>tag.trim()).filter(Boolean)).slice(0,3).forEach((tag)=>meta.appendChild(pill(`#${tag}`)));
    const time=document.createElement('span'); time.className='muted small'; time.textContent=fmtTime(contact.last_interaction_at); meta.appendChild(time);
    const snippet=document.createElement('div'); snippet.className='contact-snippet'; snippet.textContent=esc(contact.summary||'');
    item.append(top, meta, snippet);
    item.addEventListener('click',()=>{ selectedName=contact.name; editingMeta=false; renderList(); renderDetail(); });
    list.appendChild(item);
  });
}
function renderDetail() {
  const panel=$('detailPanel'); panel.replaceChildren();
  const contact=((crmData&&crmData.contacts)||[]).find((item)=>item.name===selectedName);
  if(!contact){ const empty=document.createElement('div'); empty.className='empty-detail'; empty.textContent='从左侧选择一个联系人，查看谈话时间线。'; panel.appendChild(empty); return; }
  const titleWrap=document.createElement('div');
  const title=document.createElement('h2'); title.textContent=esc(contact.name); titleWrap.appendChild(title);
  const meta=document.createElement('div'); meta.className='meta-row';
  meta.appendChild(pill(contact.kind_label||'', 'blue'));
  (contact.source_chats||[]).forEach((chat)=>meta.appendChild(pill(chat===contact.name ? `会话：${chat}` : `来自群聊：${chat}`, chat===contact.name ? '' : 'blue')));
  meta.appendChild(pill(`最近互动 ${fmtTime(contact.last_interaction_at)}`));
  titleWrap.appendChild(meta); panel.appendChild(titleWrap);
  if((contact.organizations||[]).length || (contact.identity_hints||[]).length) {
    const row=document.createElement('div'); row.className='meta-row';
    (contact.organizations||[]).forEach((org)=>row.appendChild(pill(`组织：${org}`,'blue')));
    (contact.identity_hints||[]).forEach((hint)=>row.appendChild(pill(hint)));
    panel.appendChild(row);
  }
  if((contact.signals||[]).length) {
    const label=document.createElement('p'); label.className='section-label'; label.textContent='关系信号'; panel.appendChild(label);
    const row=document.createElement('div'); row.className='meta-row'; row.style.marginTop='6px';
    contact.signals.forEach((signal)=>row.appendChild(pill(`${signal.kind}：${signal.phrase}`,'good')));
    panel.appendChild(row);
  }
  const action=contact.next_action||{};
  if(action.action){
    const box=document.createElement('div'); box.className='next-action';
    const strong=document.createElement('strong'); strong.textContent=`建议：${action.action}${action.score?`（${action.score} 分）`:''}`; box.appendChild(strong);
    if(action.why){ const why=document.createElement('div'); why.className='small muted'; why.style.marginTop='4px'; why.textContent=action.why; box.appendChild(why); }
    if(action.draft){ const draft=document.createElement('div'); draft.className='draft'; draft.textContent=action.draft; box.appendChild(draft); }
    panel.appendChild(box);
  }
  const formLabel=document.createElement('p'); formLabel.className='section-label'; formLabel.textContent='联系人档案'; panel.appendChild(formLabel);
  const form=document.createElement('div'); form.className='meta-form';
  const categories=[...new Set(((crmData&&crmData.contacts)||[]).map((item)=>item.category).filter(Boolean))];
  const categoryLabel=document.createElement('label'); categoryLabel.textContent='分类';
  const categoryInput=document.createElement('input'); categoryInput.id='metaCategory'; categoryInput.setAttribute('list','categoryOptions'); categoryInput.placeholder='如：家人 / 朋友 / 同事 / 客户'; categoryInput.value=contact.category||'';
  const datalist=document.createElement('datalist'); datalist.id='categoryOptions';
  categories.forEach((category)=>{ const option=document.createElement('option'); option.value=category; datalist.appendChild(option); });
  categoryLabel.append(categoryInput, datalist);
  const tagsLabel=document.createElement('label'); tagsLabel.textContent='标签（逗号分隔）';
  const tagsInput=document.createElement('input'); tagsInput.id='metaTags'; tagsInput.placeholder='如：AI, 读书, 投资人'; tagsInput.value=contact.tags||'';
  tagsLabel.appendChild(tagsInput);
  const notesLabel=document.createElement('label'); notesLabel.textContent='备注';
  const notesInput=document.createElement('textarea'); notesInput.id='metaNotes'; notesInput.placeholder='关于这个人的背景、约定、注意事项…'; notesInput.value=contact.notes||'';
  notesLabel.appendChild(notesInput);
  const saveRow=document.createElement('div'); saveRow.className='meta-save';
  const saveButton=document.createElement('button'); saveButton.type='button'; saveButton.textContent='保存';
  const saveStatus=document.createElement('span'); saveStatus.className='save-status';
  saveRow.append(saveButton, saveStatus);
  form.append(categoryLabel, tagsLabel, notesLabel, saveRow);
  [categoryInput, tagsInput, notesInput].forEach((input)=>input.addEventListener('input',()=>{ editingMeta=true; saveStatus.textContent=''; saveStatus.style.color=''; }));
  saveButton.addEventListener('click',()=>saveMeta(contact.name, saveStatus));
  panel.appendChild(form);
  const label=document.createElement('p'); label.className='section-label'; label.textContent='谈话时间线'; panel.appendChild(label);
  const timeline=document.createElement('div'); timeline.className='timeline';
  (contact.timeline||[]).forEach((event)=>{
    const card=document.createElement('div'); card.className='event';
    const eventMeta=document.createElement('div'); eventMeta.className='event-meta';
    const time=document.createElement('strong'); time.textContent=fmtTime(event.captured_at); eventMeta.appendChild(time);
    if(event.source_chat) eventMeta.appendChild(pill(event.source_chat,'blue'));
    if(event.source) eventMeta.appendChild(pill(event.source));
    card.appendChild(eventMeta);
    const text=document.createElement('div'); text.className='event-text'; text.textContent=esc(event.summary||''); card.appendChild(text);
    if((event.signals||[]).length){ const row=document.createElement('div'); row.className='event-signals'; event.signals.forEach((signal)=>row.appendChild(pill(`${signal.kind}：${signal.phrase}`,'good'))); card.appendChild(row); }
    if(event.image_available){
      const toggle=document.createElement('button'); toggle.type='button'; toggle.className='small'; toggle.style.marginTop='8px'; toggle.textContent='查看截图';
      toggle.addEventListener('click',()=>{ toggle.remove(); const img=document.createElement('img'); img.className='shot'; img.alt='谈话截图'; img.src=`/media/${event.capture_id}`; card.appendChild(img); });
      card.appendChild(toggle);
    }
    timeline.appendChild(card);
  });
  panel.appendChild(timeline);
}
async function refresh() {
  try {
    const [response,outreachResponse]=await Promise.all([fetch('/api/crm?limit=100',{cache:'no-store'}),fetch('/api/outreach',{cache:'no-store'})]);
    if(!response.ok) throw new Error('面板接口不可用');
    crmData=await response.json();
    renderOutreach(outreachResponse.ok ? (await outreachResponse.json()).drafts||[] : []);
    renderStats(); renderNotice();
    const running=Boolean((crmData.watch||{}).running);
    $('watchStatus').replaceChildren();
    $('watchStatus').appendChild(Object.assign(document.createElement('span'),{className:`status-dot ${running?'on':''}`}));
    $('watchStatus').appendChild(document.createTextNode(running?`watch 运行中 · ${(crmData.watch||{}).process_count||0} 个进程`:'watch 未运行'));
    $('updatedAt').textContent=`更新于 ${fmtTime(crmData.generated_at)}`;
    if(!selectedName && (crmData.contacts||[]).length) selectedName=crmData.contacts[0].name;
    renderList(); if(!editingMeta) renderDetail();
  } catch(error) { $('updatedAt').textContent=error.message; $('updatedAt').className='error small'; }
}
async function saveMeta(name, statusEl) {
  statusEl.textContent='保存中…'; statusEl.style.color='';
  try {
    const response=await fetch('/api/enrichment',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({person_name:name,category:$('metaCategory').value,tags:$('metaTags').value,notes:$('metaNotes').value})});
    if(!response.ok){ const body=await response.json().catch(()=>({})); throw new Error(body.error||'保存失败'); }
    const result=await response.json();
    const contact=((crmData&&crmData.contacts)||[]).find((item)=>item.name===name);
    if(contact){ contact.category=result.fields.category||''; contact.tags=result.fields.tags||''; contact.notes=result.fields.notes||''; }
    editingMeta=false;
    statusEl.textContent='已保存';
    renderList();
  } catch(error) { statusEl.textContent=error.message; statusEl.style.color='var(--bad)'; }
}
const DRAFT_STATUS_LABELS = {draft:'待审核', approved:'已批准', sent:'已发送', dismissed:'已驳回'};
function renderOutreach(drafts) {
  const list=$('draftList'); list.replaceChildren();
  const visible=(drafts||[]).filter((draft)=>draft.status!=='dismissed');
  if(!visible.length){ const empty=document.createElement('p'); empty.className='muted'; empty.textContent='暂无外联草稿。宿主 Agent 可通过 MCP create_outreach_drafts 写入。'; list.appendChild(empty); return; }
  visible.forEach((draft)=>{
    const card=document.createElement('div'); card.className='draft';
    const head=document.createElement('div'); head.className='draft-head';
    const name=document.createElement('span'); name.className='draft-name'; name.textContent=esc(draft.person_name);
    name.addEventListener('click',()=>{ selectedName=draft.person_name; editingMeta=false; renderList(); renderDetail(); });
    head.appendChild(name);
    head.appendChild(pill(DRAFT_STATUS_LABELS[draft.status]||draft.status, draft.status==='approved'?'good':draft.status==='sent'?'blue':''));
    if(draft.campaign) head.appendChild(pill(draft.campaign));
    if(draft.topic) head.appendChild(pill(draft.topic));
    head.appendChild(pill(draft.send_mode==='computer_use'?'computer use':'手动发送', draft.send_mode==='computer_use'?'warn':''));
    const time=document.createElement('span'); time.className='muted small'; time.textContent=fmtTime(draft.updated_at); head.appendChild(time);
    const text=document.createElement('div'); text.className='draft-text'; text.textContent=esc(draft.draft_text);
    card.append(head, text);
    const actions=document.createElement('div'); actions.className='draft-actions';
    const addButton=(label, action)=>{ const button=document.createElement('button'); button.type='button'; button.textContent=label; button.addEventListener('click',()=>draftAction(draft.id, action)); actions.appendChild(button); };
    if(draft.status==='draft'){ addButton('批准','approve'); addButton('驳回','dismiss'); }
    else if(draft.status==='approved'){ addButton('标记已发送','mark_sent'); addButton('驳回','dismiss'); }
    if(actions.childElementCount) card.appendChild(actions);
    list.appendChild(card);
  });
}
async function draftAction(id, action) {
  try {
    const response=await fetch('/api/outreach',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({draft_id:id,action})});
    if(!response.ok){ const body=await response.json().catch(()=>({})); throw new Error(body.error||'操作失败'); }
    refresh();
  } catch(error) { $('updatedAt').textContent=error.message; $('updatedAt').className='error small'; }
}
$('refresh').addEventListener('click',refresh);
$('contactSearch').addEventListener('input',(event)=>{ searchText=event.target.value.trim(); renderList(); });
refresh(); setInterval(refresh,10000);
</script>
</body>
</html>
"""
