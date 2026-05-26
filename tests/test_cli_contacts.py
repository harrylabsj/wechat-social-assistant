import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from wsa.cli import main
from wsa.store import ingest_capture, init_db


class ContactsCommandTests(unittest.TestCase):
    def test_contacts_lists_names_that_can_be_used_for_contact_filters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "群成员A\n"
                    "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-26T22:21:20+08:00",
            )
            ingest_capture(
                db_path,
                raw_text="联系人B\n你看，我能做些什么。喜欢尝试新鲜事物。",
                contact_hint="联系人B",
                source="test",
                captured_at="2026-05-26T22:22:20+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "contacts"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("# 联系人索引", output)
        self.assertIn("| 名称 | 类型 | 来源群/会话 | 最近出现 | 线索 | 关系信号 |", output)
        self.assertIn("| 群成员A | 群内联系人 | 项目交流群（3） | 2026-05-26 22:21 |  | 项目/合作 |", output)
        self.assertIn("| 项目交流群（3） | 群聊 |  | 2026-05-26 22:21 |  | 项目/合作 |", output)
        self.assertIn("| 联系人B | 私聊/单聊 |  | 2026-05-26 22:22 |  |  |", output)

    def test_contacts_query_filters_by_name_or_source_group(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "群成员A\n"
                    "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-26T22:21:20+08:00",
            )
            ingest_capture(
                db_path,
                raw_text="联系人B\n你看，我能做些什么。喜欢尝试新鲜事物。",
                contact_hint="联系人B",
                source="test",
                captured_at="2026-05-26T22:22:20+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "contacts", "--query", "项目交流"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("| 群成员A |", output)
        self.assertIn("| 项目交流群（3） |", output)
        self.assertNotIn("| 联系人B |", output)

    def test_contacts_accepts_contact_option_as_query_alias(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "群成员A\n"
                    "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-26T22:21:20+08:00",
            )
            ingest_capture(
                db_path,
                raw_text="联系人B\n你看，我能做些什么。喜欢尝试新鲜事物。",
                contact_hint="联系人B",
                source="test",
                captured_at="2026-05-26T22:22:20+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "contacts", "--contact", "项目交流"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("| 群成员A |", output)
        self.assertIn("| 项目交流群（3） |", output)
        self.assertNotIn("| 联系人B |", output)

    def test_contacts_query_ignores_spaces_and_brackets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "群成员A\n"
                    "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-26T22:21:20+08:00",
            )
            ingest_capture(
                db_path,
                raw_text="陈明 DANIEL\n我是陆陈明 DANIEL 示例资本。幸会！",
                contact_hint="陈明 DANIEL",
                source="test",
                captured_at="2026-05-26T22:22:20+08:00",
            )

            group_stdout = io.StringIO()
            with contextlib.redirect_stdout(group_stdout):
                group_exit_code = main(["--db", str(db_path), "contacts", "--query", "项目交流群3"])
            name_stdout = io.StringIO()
            with contextlib.redirect_stdout(name_stdout):
                name_exit_code = main(["--db", str(db_path), "contacts", "--query", "陈明daniel"])

        group_output = group_stdout.getvalue()
        name_output = name_stdout.getvalue()
        self.assertEqual(0, group_exit_code)
        self.assertEqual(0, name_exit_code)
        self.assertIn("| 项目交流群（3） |", group_output)
        self.assertIn("| 群成员A |", group_output)
        self.assertIn("| 陈明 DANIEL |", name_output)

    def test_contacts_query_matches_organization_or_identity_hints(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="陈明 DANIEL\n我是陆陈明 DANIEL 示例资本。幸会！\n陈明\nDaniel Chen",
                contact_hint="陈明 DANIEL",
                source="test",
                captured_at="2026-05-26T22:22:20+08:00",
            )
            ingest_capture(
                db_path,
                raw_text="联系人B\n你看，我能做些什么。喜欢尝试新鲜事物。",
                contact_hint="联系人B",
                source="test",
                captured_at="2026-05-26T22:23:20+08:00",
            )

            org_stdout = io.StringIO()
            with contextlib.redirect_stdout(org_stdout):
                org_exit_code = main(["--db", str(db_path), "contacts", "--query", "示例资本"])
            identity_stdout = io.StringIO()
            with contextlib.redirect_stdout(identity_stdout):
                identity_exit_code = main(["--db", str(db_path), "contacts", "--query", "DanielChen"])

        org_output = org_stdout.getvalue()
        identity_output = identity_stdout.getvalue()
        self.assertEqual(0, org_exit_code)
        self.assertEqual(0, identity_exit_code)
        self.assertIn("| 陈明 DANIEL |", org_output)
        self.assertIn("| 陈明 DANIEL | 私聊/单聊 |  | 2026-05-26 22:22 | 陈明, Daniel Chen, 示例资本 |  |", org_output)
        self.assertNotIn("| 联系人B |", org_output)
        self.assertIn("| 陈明 DANIEL |", identity_output)

    def test_contacts_query_empty_state_names_the_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="联系人B\n你看，我能做些什么。喜欢尝试新鲜事物。",
                contact_hint="联系人B",
                source="test",
                captured_at="2026-05-26T22:22:20+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "contacts", "--query", "群成员A"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("没有找到匹配「群成员A」的联系人。", output)


if __name__ == "__main__":
    unittest.main()
