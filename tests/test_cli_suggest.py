import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from wsa.cli import main
from wsa.store import ingest_capture, init_db


AS_OF = "2026-05-28T12:00:00+08:00"


class SuggestCommandTests(unittest.TestCase):
    def test_suggest_default_filters_recent_low_priority_contacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="李四\n最近看到一篇文章，挺有意思。",
                contact_hint="李四",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
            )
            ingest_capture(
                db_path,
                raw_text="孙八\n下周约饭吗？",
                contact_hint="孙八",
                source="test",
                captured_at="2026-05-26T09:01:00+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "suggest", "--as-of", AS_OF])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("| 孙八 |", output)
        self.assertNotIn("| 李四 |", output)

    def test_suggest_min_score_zero_can_show_all_contacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="李四\n最近看到一篇文章，挺有意思。",
                contact_hint="李四",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "suggest", "--min-score", "0", "--as-of", AS_OF])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("| 李四 | 20 | 低（没有强关系信号，可先不主动联系或仅轻量问候） |", output)

    def test_suggest_contact_filters_to_named_contact_instead_of_global_top(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="赵六\n上次的问题你还没回复我，方便的时候看下。",
                contact_hint="赵六",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
            )
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "群成员A\n"
                    "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-26T09:01:00+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "suggest", "--contact", "群成员A", "--as-of", AS_OF])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("| 群成员A |", output)
        self.assertIn("来自群：项目交流群（3）", output)
        self.assertNotIn("| 赵六 |", output)

    def test_suggest_contact_exact_name_does_not_include_other_speakers_who_mention_them(self):
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
                captured_at="2026-05-26T09:01:00+08:00",
            )
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "Alice\n"
                    "群成员A 这个项目我还没回复，今天需要推进一下。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-27T09:01:00+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "suggest", "--contact", "群成员A", "--as-of", AS_OF])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("| 群成员A |", output)
        self.assertNotIn("| Alice |", output)

    def test_suggest_contact_can_filter_by_source_group(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="赵六\n上次的问题你还没回复我，方便的时候看下。",
                contact_hint="赵六",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
            )
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "群成员A\n"
                    "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-26T09:01:00+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "suggest", "--contact", "项目交流", "--as-of", AS_OF])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("| 群成员A |", output)
        self.assertIn("项目跟进", output)
        self.assertNotIn("| 赵六 |", output)

    def test_suggest_contact_can_filter_by_organization_hint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="陈明 DANIEL\n我是陆陈明 DANIEL 示例资本。幸会！\n陈明\nDaniel Chen",
                contact_hint="陈明 DANIEL",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
            )
            ingest_capture(
                db_path,
                raw_text="联系人B\n你看，我能做些什么。喜欢尝试新鲜事物。",
                contact_hint="联系人B",
                source="test",
                captured_at="2026-05-26T09:01:00+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    ["--db", str(db_path), "suggest", "--contact", "示例资本", "--min-score", "0", "--as-of", AS_OF]
                )

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("| 陈明 DANIEL |", output)
        self.assertNotIn("| 联系人B |", output)

    def test_suggest_contact_empty_state_names_the_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="孙八\n下周约饭吗？",
                contact_hint="孙八",
                source="test",
                captured_at="2026-05-26T09:01:00+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "suggest", "--contact", "群成员A", "--as-of", AS_OF])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("没有找到匹配「群成员A」的跟进建议。", output)
        self.assertNotIn("暂无需要跟进的联系人。", output)

    def test_suggest_contact_empty_state_mentions_threshold_when_low_score_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="李四\n最近看到一篇文章，挺有意思。",
                contact_hint="李四",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "suggest", "--contact", "李四", "--as-of", AS_OF])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("匹配「李四」的跟进建议低于当前阈值 45", output)
        self.assertIn("最高 20 分", output)
        self.assertIn("--min-score 0", output)
        self.assertNotIn("没有找到匹配「李四」的跟进建议。", output)


if __name__ == "__main__":
    unittest.main()
