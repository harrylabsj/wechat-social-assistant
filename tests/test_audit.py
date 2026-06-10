import json
import tempfile
import unittest
from pathlib import Path

from wsa.audit import (
    build_audit_report,
    delete_contact_data,
    export_local_data,
    render_audit_report_markdown,
)
from wsa.feedback import record_feedback
from wsa.sources import import_relationship_sources, list_relationship_sources
from wsa.store import ingest_capture, init_db


class AuditAndDataControlTests(unittest.TestCase):
    def test_audit_export_and_delete_contact_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            _seed_audit_data(root, db_path)
            export_path = root / "export" / "wsa-export.json"

            audit = build_audit_report(db_path)
            markdown = render_audit_report_markdown(audit)
            export_result = export_local_data(db_path, out_path=export_path)
            payload = json.loads(export_path.read_text(encoding="utf-8"))
            dry_run = delete_contact_data(db_path, "张三", dry_run=True)
            before_delete_sources = list_relationship_sources(db_path, person_name="张三")
            screenshot = root / "data" / "captures" / "zhangsan.png"
            screenshot_exists_after_dry_run = screenshot.exists()
            delete_result = delete_contact_data(db_path, "张三")
            after_delete_sources = list_relationship_sources(db_path, person_name="张三")
            after_audit = build_audit_report(db_path)
            screenshot_exists_after_delete = screenshot.exists()

        self.assertEqual(1, audit.table_counts["captures"])
        self.assertEqual(1, audit.table_counts["relationship_sources"])
        self.assertIn("# 本地数据审计", markdown)
        self.assertEqual(export_path, export_result.out_path)
        self.assertEqual(1, export_result.table_counts["people"])
        self.assertIn("people", payload["tables"])
        self.assertEqual("张三", payload["tables"]["people"][0]["name"])
        self.assertEqual(1, dry_run.removed_captures)
        self.assertEqual(1, dry_run.removed_screenshots)
        self.assertTrue(screenshot_exists_after_dry_run)
        self.assertEqual(1, len(before_delete_sources))
        self.assertTrue(dry_run.dry_run)
        self.assertEqual(1, delete_result.removed_people)
        self.assertEqual(1, delete_result.removed_sources)
        self.assertEqual(1, delete_result.removed_screenshots)
        self.assertFalse(screenshot_exists_after_delete)
        self.assertEqual([], after_delete_sources)
        self.assertEqual(0, after_audit.table_counts["people"])
        self.assertEqual(0, after_audit.table_counts["captures"])

    def test_delete_contact_keeps_screenshot_still_referenced_by_another_capture(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            image = root / "shared.png"
            image.write_bytes(b"shared image")
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="张三\n下周方便聊聊这个项目吗？",
                contact_hint="张三",
                source="image",
                captured_at="2026-05-27T09:00:00+08:00",
                image_path=str(image),
            )
            ingest_capture(
                db_path,
                raw_text="李四\n下周方便聊聊这个项目吗？",
                contact_hint="李四",
                source="image",
                captured_at="2026-05-27T09:05:00+08:00",
                image_path=str(image),
            )

            result = delete_contact_data(db_path, "张三")
            image_exists_after_delete = image.exists()

        self.assertEqual(1, result.removed_captures)
        self.assertEqual(0, result.removed_screenshots)
        self.assertTrue(image_exists_after_delete)


def _seed_audit_data(root: Path, db_path: Path) -> None:
    init_db(db_path)
    captures_dir = root / "data" / "captures"
    captures_dir.mkdir(parents=True)
    image = captures_dir / "zhangsan.png"
    image.write_bytes(b"zhangsan screenshot")
    ingest_capture(
        db_path,
        raw_text="张三\n你上次提到的问题，我这边还没回复，今天补给你。",
        contact_hint="张三",
        source="test",
        captured_at="2026-05-27T09:00:00+08:00",
        image_path=str(image),
    )
    record_feedback(
        db_path,
        person_name="张三",
        action="good_draft",
        created_at="2026-05-27T10:00:00+08:00",
    )
    source_file = root / "contacts.vcf"
    source_file.write_text(
        "\n".join(["BEGIN:VCARD", "FN:张三", "ORG:星火科技", "END:VCARD"]),
        encoding="utf-8",
    )
    import_relationship_sources(
        db_path,
        paths=[source_file],
        imported_at="2026-05-27T10:30:00+08:00",
    )


if __name__ == "__main__":
    unittest.main()
