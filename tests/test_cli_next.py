import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from wsa.cli import main
from wsa.store import ingest_capture, init_db


class NextCommandTests(unittest.TestCase):
    def test_next_prints_top_followup_with_full_draft(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "群成员A\n"
                    "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。或者咱们打算往哪个方向做，我再\n"
                    "着重研究一下。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-26T22:21:20+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "next"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("# 下一条跟进", output)
        self.assertIn("人：群成员A", output)
        self.assertIn("动作：项目跟进", output)
        self.assertIn("分数：50", output)
        self.assertIn("跟进强度：中（有明确关系信号，适合跟进）", output)
        self.assertIn("最近互动：2026-05-26 22:21", output)
        self.assertIn("原因：来自群：项目交流群（3）；对方提到项目/合作进展", output)
        self.assertIn("草稿：群成员A，上次你在「项目交流群（3）」里提到", output)
        self.assertIn("我这边可以继续补充。", output)

    def test_next_draft_only_prints_copyable_draft_without_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "群成员A\n"
                    "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。或者咱们打算往哪个方向做，我再\n"
                    "着重研究一下。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-26T22:21:20+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "next", "--draft-only"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertTrue(output.startswith("群成员A，上次你在「项目交流群（3）」里提到"))
        self.assertIn("我这边可以继续补充。", output)
        self.assertNotIn("# 下一条跟进", output)
        self.assertNotIn("分数：", output)
        self.assertNotIn("原因：", output)

    def test_next_contact_filters_to_named_contact_instead_of_global_top(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="赵六\n上次的问题你还没回复我，方便的时候看下。",
                contact_hint="赵六",
                source="test",
                captured_at="2026-05-26T22:20:20+08:00",
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
                captured_at="2026-05-26T22:21:20+08:00",
                image_path="/tmp/wechat-sunny.png",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "next", "--contact", "群成员A"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("人：群成员A", output)
        self.assertIn("动作：项目跟进", output)
        self.assertIn("证据会话：项目交流群（3）", output)
        self.assertIn("证据时间：2026-05-26 22:21", output)
        self.assertIn("证据截图：/tmp/wechat-sunny.png", output)
        self.assertNotIn("人：赵六", output)

    def test_next_contact_exact_name_does_not_pick_other_speaker_who_mentions_them(self):
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
                raw_text=(
                    "项目交流群（3）\n"
                    "Alice\n"
                    "群成员A 这个项目我还没回复，今天需要推进一下。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-27T22:21:20+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "next", "--contact", "群成员A"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("人：群成员A", output)
        self.assertNotIn("人：Alice", output)

    def test_next_contact_can_filter_by_source_group(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="赵六\n上次的问题你还没回复我，方便的时候看下。",
                contact_hint="赵六",
                source="test",
                captured_at="2026-05-26T22:20:20+08:00",
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
                captured_at="2026-05-26T22:21:20+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "next", "--contact", "项目交流"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("人：群成员A", output)
        self.assertIn("原因：来自群：项目交流群（3）", output)
        self.assertNotIn("人：赵六", output)

    def test_next_evidence_follows_signal_capture_when_latest_capture_is_lightweight(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="李四\n下周方便聊聊你那个新项目吗？",
                contact_hint="李四",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
                image_path="/tmp/li-si-signal.png",
            )
            ingest_capture(
                db_path,
                raw_text="李四\n最近看到一篇文章，挺有意思。",
                contact_hint="李四",
                source="test",
                captured_at="2026-05-26T09:30:00+08:00",
                image_path="/tmp/li-si-latest.png",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "next", "--contact", "李四"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("动作：确认时间", output)
        self.assertIn("证据时间：2026-05-26 09:00", output)
        self.assertIn("证据截图：/tmp/li-si-signal.png", output)
        self.assertNotIn("证据截图：/tmp/li-si-latest.png", output)

    def test_next_speaker_evidence_follows_signal_capture_when_latest_speaker_message_is_lightweight(self):
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
                captured_at="2026-05-26T09:00:00+08:00",
                image_path="/tmp/sunny-signal.png",
            )
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "群成员A\n"
                    "可以参考一下这家"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-26T09:30:00+08:00",
                image_path="/tmp/sunny-latest.png",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "next", "--contact", "群成员A"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("人：群成员A", output)
        self.assertIn("动作：项目跟进", output)
        self.assertIn("证据时间：2026-05-26 09:00", output)
        self.assertIn("证据截图：/tmp/sunny-signal.png", output)
        self.assertNotIn("证据截图：/tmp/sunny-latest.png", output)

    def test_next_draft_only_omits_evidence_metadata(self):
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
                image_path="/tmp/wechat-sunny.png",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "next", "--contact", "群成员A", "--draft-only"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertTrue(output.startswith("群成员A，上次你在「项目交流群（3）」里提到"))
        self.assertNotIn("证据会话：", output)
        self.assertNotIn("证据截图：", output)

    def test_next_contact_matches_group_name_without_brackets(self):
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

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "next", "--contact", "项目交流群3"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("人：群成员A", output)
        self.assertIn("原因：来自群：项目交流群（3）", output)

    def test_next_contact_can_filter_by_organization_hint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="陈明 DANIEL\n我是陆陈明 DANIEL 示例资本。幸会！\n陈明\nDaniel Chen",
                contact_hint="陈明 DANIEL",
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
                exit_code = main(
                    ["--db", str(db_path), "next", "--contact", "示例资本", "--min-score", "0"]
                )

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("人：陈明 DANIEL", output)
        self.assertIn("跟进强度：低（没有强关系信号，可先不主动联系或仅轻量问候）", output)
        self.assertNotIn("人：联系人B", output)

    def test_next_prints_empty_state_when_no_suggestion_matches_threshold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="李四\n最近看到一篇文章，挺有意思。",
                contact_hint="李四",
                source="test",
                captured_at="2026-05-26T22:21:20+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "next"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("现有跟进建议低于当前阈值 45", output)
        self.assertIn("最高 20 分", output)
        self.assertIn("--min-score 0", output)
        self.assertNotIn("# 下一条跟进", output)

    def test_next_contact_empty_state_mentions_threshold_when_low_score_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="李四\n最近看到一篇文章，挺有意思。",
                contact_hint="李四",
                source="test",
                captured_at="2026-05-26T22:21:20+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "next", "--contact", "李四"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("匹配「李四」的跟进建议低于当前阈值 45", output)
        self.assertIn("最高 20 分", output)
        self.assertIn("--min-score 0", output)
        self.assertNotIn("没有找到匹配「李四」的跟进建议。", output)

    def test_next_contact_empty_state_names_the_filter(self):
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
                exit_code = main(["--db", str(db_path), "next", "--contact", "群成员A"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("没有找到匹配「群成员A」的跟进建议。", output)
        self.assertNotIn("暂无需要跟进的联系人。", output)

    def test_next_initializes_missing_database_and_prints_empty_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "next"])

            output = stdout.getvalue()
            self.assertEqual(0, exit_code)
            self.assertTrue(db_path.exists())
            self.assertIn("暂无需要跟进的联系人。", output)
            self.assertNotIn("no such table", output)


if __name__ == "__main__":
    unittest.main()
