import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from wsa.cli import main
from wsa.store import ingest_capture, init_db


class ProfilesCommandTests(unittest.TestCase):
    def test_profiles_contact_filters_to_matching_group_speaker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "群成员A\n"
                    "可以参考一下这家\n"
                    "群成员A\n"
                    "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。\n"
                    "示例材料.docx\n"
                    "同意，先做起来。名称里要有龙虾，以便搜索。"
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
                exit_code = main(["--db", str(db_path), "profiles", "--contact", "群成员A"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("## 群成员A", output)
        self.assertIn("来源群/会话：项目交流群（3）", output)
        self.assertIn("关系信号：项目/合作", output)
        self.assertNotIn("## 项目交流群（3）", output)
        self.assertNotIn("## 联系人B", output)

    def test_profiles_contact_empty_state_names_the_filter(self):
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
                exit_code = main(["--db", str(db_path), "profiles", "--contact", "群成员A"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("没有找到匹配「群成员A」的联系人档案。", output)
        self.assertNotIn("暂无联系人档案。", output)

    def test_profiles_contact_matches_organization_hint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="陈明 DANIEL\n我是陆陈明 DANIEL 示例资本。幸会！\nDaniel Chen",
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

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "profiles", "--contact", "示例资本"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("## 陈明 DANIEL", output)
        self.assertIn("机构/公司：示例资本", output)
        self.assertNotIn("## 联系人B", output)

    def test_profiles_contact_searches_all_profiles_before_applying_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="赵六\n上次的问题你还没回复我，方便的时候看下。",
                contact_hint="赵六",
                source="test",
                captured_at="2026-05-26T22:22:20+08:00",
            )
            ingest_capture(
                db_path,
                raw_text="李四\n最近看到一篇文章，挺有意思。",
                contact_hint="李四",
                source="test",
                captured_at="2026-05-26T22:21:20+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "profiles", "--contact", "李四", "--limit", "1"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("## 李四", output)
        self.assertIn("最近看到一篇文章，挺有意思。", output)
        self.assertNotIn("没有找到匹配「李四」的联系人档案。", output)


if __name__ == "__main__":
    unittest.main()
