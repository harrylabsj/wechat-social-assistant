import tempfile
import unittest
from pathlib import Path

from wsa.profiles import build_profiles
from wsa.sources import (
    import_relationship_sources,
    list_relationship_sources,
    render_relationship_sources_markdown,
)
from wsa.store import init_db


class RelationshipSourceTests(unittest.TestCase):
    def test_imports_local_contacts_calendar_meetings_obsidian_and_email(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            init_db(db_path)
            files = _write_source_fixtures(root)

            dry_run = import_relationship_sources(db_path, paths=files, dry_run=True)
            before = list_relationship_sources(db_path)
            result = import_relationship_sources(
                db_path,
                paths=files,
                imported_at="2026-05-27T12:00:00+08:00",
            )
            second = import_relationship_sources(
                db_path,
                paths=files,
                imported_at="2026-05-27T12:00:00+08:00",
            )
            records = list_relationship_sources(db_path)
            markdown = render_relationship_sources_markdown(records)
            profiles = build_profiles(db_path)

        self.assertEqual(0, dry_run.imported_count)
        self.assertEqual([], before)
        self.assertEqual(
            {
                "contacts": 1,
                "calendar": 2,
                "meeting": 2,
                "obsidian": 1,
                "email": 2,
            },
            result.by_type,
        )
        self.assertEqual(8, result.imported_count)
        self.assertEqual(0, second.imported_count)
        self.assertEqual(8, len(records))
        self.assertIn("# 多入口关系来源", markdown)
        self.assertIn("| 张三 | calendar | 医疗AI路演 |", markdown)
        self.assertIn("| 李四 | email | 医疗AI合作进展 |", markdown)

        profiles_by_name = {profile.name: profile for profile in profiles}
        self.assertIn("赵六", profiles_by_name)
        self.assertIn("未来医院", profiles_by_name["赵六"].organizations)
        self.assertTrue(any("医务部主任" in clue for clue in profiles_by_name["赵六"].identity_hints))
        self.assertIn("张三", profiles_by_name)
        self.assertTrue(any("医疗AI路演" in item for item in profiles_by_name["张三"].recent_contents))
        self.assertTrue(any("年度复盘" in item for item in profiles_by_name["李四"].recent_contents))

    def test_source_listing_can_filter_by_contact_and_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            init_db(db_path)
            import_relationship_sources(db_path, paths=_write_source_fixtures(root))

            zhang = list_relationship_sources(db_path, person_name="张三")
            calendar = list_relationship_sources(db_path, source_type="calendar")

        self.assertEqual({"张三"}, {record.person_name for record in zhang})
        self.assertEqual({"calendar"}, {record.source_type for record in calendar})
        self.assertEqual({"张三", "王五"}, {record.person_name for record in calendar})

    def test_import_directory_skips_unknown_binary_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            source_dir = root / "sources"
            source_dir.mkdir()
            (source_dir / "meeting.md").write_text(
                "# 项目会\n\n日期：2026-05-29\n参会人：张三\n\n讨论项目计划。",
                encoding="utf-8",
            )
            (source_dir / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff")
            init_db(db_path)

            result = import_relationship_sources(db_path, paths=[source_dir], dry_run=True)

        self.assertEqual(1, result.parsed_count)
        self.assertEqual(1, result.skipped_count)
        self.assertEqual({"meeting": 1}, result.by_type)

    def test_explicit_text_kind_skips_files_that_are_not_utf8(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            binary_file = root / "photo.png"
            binary_file.write_bytes(b"\xff\xfe\x00\x00")
            init_db(db_path)

            result = import_relationship_sources(
                db_path,
                paths=[binary_file],
                kind="meeting",
                dry_run=True,
            )

        self.assertEqual(0, result.parsed_count)
        self.assertEqual(1, result.skipped_count)


def _write_source_fixtures(root: Path) -> list[Path]:
    contacts = root / "contacts.vcf"
    contacts.write_text(
        "\n".join(
            [
                "BEGIN:VCARD",
                "VERSION:3.0",
                "FN:赵六",
                "ORG:未来医院",
                "TITLE:医务部主任",
                "EMAIL:zhaoliu@example.com",
                "TEL:+86 13800000000",
                "NOTE:关注医疗AI落地",
                "END:VCARD",
            ]
        ),
        encoding="utf-8",
    )
    calendar = root / "calendar.ics"
    calendar.write_text(
        "\n".join(
            [
                "BEGIN:VCALENDAR",
                "BEGIN:VEVENT",
                "SUMMARY:医疗AI路演",
                "DTSTART:20260528T100000",
                "DESCRIPTION:讨论医疗AI落地和合作机会",
                "ATTENDEE;CN=张三:mailto:zhangsan@example.com",
                "ATTENDEE;CN=王五:mailto:wangwu@example.com",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        ),
        encoding="utf-8",
    )
    meeting = root / "meeting.md"
    meeting.write_text(
        "# 医疗AI闭门会\n\n日期：2026-05-29\n参会人：张三、李四\n\n讨论年度复盘和下季度合作计划。",
        encoding="utf-8",
    )
    obsidian = root / "Obsidian Vault" / "社交圈" / "人脉"
    obsidian.mkdir(parents=True)
    (obsidian / "陈明.md").write_text(
        "# 陈明\n\n## 手工补充\n- 公司：示例资本\n- 职位/角色：投资人\n- 认识场景：校友会\n",
        encoding="utf-8",
    )
    (obsidian / "索引.md").write_text("# 人脉索引\n\n- [[陈明]]\n", encoding="utf-8")
    email = root / "thread.eml"
    email.write_text(
        "\n".join(
            [
                "From: 李四 <lisi@example.com>",
                "To: 张三 <zhangsan@example.com>",
                "Date: Wed, 27 May 2026 11:00:00 +0800",
                "Subject: 医疗AI合作进展",
                "",
                "张三你好，年度复盘后我们可以继续推进医疗AI合作。",
            ]
        ),
        encoding="utf-8",
    )
    return [contacts, calendar, meeting, root / "Obsidian Vault", email]


if __name__ == "__main__":
    unittest.main()
