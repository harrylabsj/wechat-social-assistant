from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .store import connect, init_db, now_iso


AUDIT_TABLES = (
    "people",
    "captures",
    "capture_signals",
    "contact_feedback",
    "relationship_candidates",
    "contact_enrichments",
    "relationship_sources",
)


@dataclass(frozen=True)
class AuditReport:
    db_path: Path
    generated_at: str
    table_counts: dict[str, int]
    data_paths: dict[str, str]


@dataclass(frozen=True)
class ExportDataResult:
    out_path: Path
    generated_at: str
    table_counts: dict[str, int]


@dataclass(frozen=True)
class DeleteContactResult:
    person_name: str
    removed_people: int
    removed_captures: int
    removed_signals: int
    removed_feedback: int
    removed_candidates: int
    removed_enrichments: int
    removed_sources: int
    dry_run: bool = False


def build_audit_report(db_path: Path | str) -> AuditReport:
    init_db(db_path)
    db = Path(db_path)
    with connect(db) as conn:
        counts = _table_counts(conn)
    return AuditReport(
        db_path=db,
        generated_at=now_iso(),
        table_counts=counts,
        data_paths={
            "database": str(db),
            "captures": str(db.parent / "captures"),
            "reports": str(db.parent.parent / "reports") if db.parent.name == "data" else str(db.parent / "reports"),
        },
    )


def render_audit_report_markdown(report: AuditReport) -> str:
    lines = [
        "# 本地数据审计",
        "",
        f"- 生成时间：{report.generated_at}",
        f"- 数据库：{report.data_paths['database']}",
        f"- 截图目录：{report.data_paths['captures']}",
        f"- 报告目录：{report.data_paths['reports']}",
        "",
        "| 表 | 行数 |",
        "|---|---:|",
    ]
    for table in AUDIT_TABLES:
        lines.append(f"| {table} | {report.table_counts.get(table, 0)} |")
    return "\n".join(lines) + "\n"


def audit_report_to_dict(report: AuditReport) -> dict[str, Any]:
    return {
        "db_path": str(report.db_path),
        "generated_at": report.generated_at,
        "table_counts": dict(report.table_counts),
        "data_paths": dict(report.data_paths),
    }


def export_local_data(db_path: Path | str, *, out_path: Path | str) -> ExportDataResult:
    init_db(db_path)
    out = Path(out_path)
    generated_at = now_iso()
    with connect(db_path) as conn:
        tables = {table: _table_rows(conn, table) for table in AUDIT_TABLES}
        counts = {table: len(rows) for table, rows in tables.items()}
    payload = {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "db_path": str(Path(db_path)),
        "tables": tables,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ExportDataResult(out_path=out, generated_at=generated_at, table_counts=counts)


def delete_contact_data(
    db_path: Path | str,
    person_name: str,
    *,
    dry_run: bool = False,
) -> DeleteContactResult:
    init_db(db_path)
    name = person_name.strip()
    if not name:
        raise ValueError("person_name is required")
    with connect(db_path) as conn:
        impact = _delete_contact_impact(conn, name)
        if not dry_run:
            _delete_contact_rows(conn, name, impact["person_ids"], impact["capture_ids"])
            conn.commit()
    return DeleteContactResult(
        person_name=name,
        removed_people=impact["people"],
        removed_captures=impact["captures"],
        removed_signals=impact["signals"],
        removed_feedback=impact["feedback"],
        removed_candidates=impact["candidates"],
        removed_enrichments=impact["enrichments"],
        removed_sources=impact["sources"],
        dry_run=dry_run,
    )


def delete_result_to_dict(result: DeleteContactResult) -> dict[str, Any]:
    return {
        "person_name": result.person_name,
        "removed_people": result.removed_people,
        "removed_captures": result.removed_captures,
        "removed_signals": result.removed_signals,
        "removed_feedback": result.removed_feedback,
        "removed_candidates": result.removed_candidates,
        "removed_enrichments": result.removed_enrichments,
        "removed_sources": result.removed_sources,
        "dry_run": result.dry_run,
    }


def _table_counts(conn) -> dict[str, int]:
    return {
        table: int(conn.execute(f"select count(*) from {table}").fetchone()[0])
        for table in AUDIT_TABLES
    }


def _table_rows(conn, table: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(f"select * from {table} order by id").fetchall()]


def _delete_contact_impact(conn, name: str) -> dict[str, Any]:
    person_ids = [int(row["id"]) for row in conn.execute("select id from people where name = ?", (name,)).fetchall()]
    capture_ids = _capture_ids(conn, person_ids)
    return {
        "person_ids": person_ids,
        "capture_ids": capture_ids,
        "people": len(person_ids),
        "captures": len(capture_ids),
        "signals": _count_by_ids(conn, "capture_signals", "capture_id", capture_ids),
        "feedback": _count_where(conn, "contact_feedback", "person_name = ?", (name,)),
        "candidates": _count_where(conn, "relationship_candidates", "name = ? or source_chat = ?", (name, name)),
        "enrichments": _count_where(conn, "contact_enrichments", "person_name = ?", (name,)),
        "sources": _count_where(conn, "relationship_sources", "person_name = ?", (name,)),
    }


def _delete_contact_rows(conn, name: str, person_ids: list[int], capture_ids: list[int]) -> None:
    _delete_by_ids(conn, "capture_signals", "capture_id", capture_ids)
    _delete_by_ids(conn, "captures", "id", capture_ids)
    _delete_by_ids(conn, "people", "id", person_ids)
    conn.execute("delete from contact_feedback where person_name = ?", (name,))
    conn.execute("delete from relationship_candidates where name = ? or source_chat = ?", (name, name))
    conn.execute("delete from contact_enrichments where person_name = ?", (name,))
    conn.execute("delete from relationship_sources where person_name = ?", (name,))


def _capture_ids(conn, person_ids: list[int]) -> list[int]:
    if not person_ids:
        return []
    placeholders = ", ".join("?" for _ in person_ids)
    return [
        int(row["id"])
        for row in conn.execute(
            f"select id from captures where person_id in ({placeholders})",
            person_ids,
        ).fetchall()
    ]


def _count_by_ids(conn, table: str, column: str, ids: list[int]) -> int:
    if not ids:
        return 0
    placeholders = ", ".join("?" for _ in ids)
    return int(conn.execute(f"select count(*) from {table} where {column} in ({placeholders})", ids).fetchone()[0])


def _delete_by_ids(conn, table: str, column: str, ids: list[int]) -> None:
    if not ids:
        return
    placeholders = ", ".join("?" for _ in ids)
    conn.execute(f"delete from {table} where {column} in ({placeholders})", ids)


def _count_where(conn, table: str, where: str, params: tuple[Any, ...]) -> int:
    return int(conn.execute(f"select count(*) from {table} where {where}", params).fetchone()[0])
