import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from wsa.cli import main
from wsa.store import ingest_capture, init_db


AS_OF = "2026-05-28T12:00:00+08:00"


def run_cli(argv: list[str]) -> tuple[int, str]:
    if "brief" in argv and "--as-of" not in argv:
        argv = [*argv, "--as-of", AS_OF]
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            exit_code = main(argv)
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 1
    return exit_code, stdout.getvalue() + stderr.getvalue()


class BriefCommandTests(unittest.TestCase):
    def test_brief_combines_profile_and_next_suggestion_for_group_speaker(self):
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
                image_path="/tmp/wechat-sunny.png",
            )

            exit_code, output = run_cli(["--db", str(db_path), "brief", "群成员A"])

        self.assertEqual(0, exit_code)
        self.assertIn("# 联系人简报：群成员A", output)
        self.assertIn("- 类型：群内联系人", output)
        self.assertIn("- 来源群/会话：项目交流群（3）", output)
        self.assertIn("- 关系信号：项目/合作", output)
        self.assertIn("## 最近联系内容", output)
        self.assertIn("简单整理了一些我的想法", output)
        self.assertIn("## 最近采集证据", output)
        self.assertIn("- 会话：项目交流群（3）", output)
        self.assertIn("- 采集时间：2026-05-26 22:21", output)
        self.assertIn("- 截图：/tmp/wechat-sunny.png", output)
        self.assertIn("## 下一步", output)
        self.assertIn("- 动作：项目跟进", output)
        self.assertIn("- 分数：50", output)
        self.assertIn("草稿：群成员A，上次你在「项目交流群（3）」里提到", output)

    def test_brief_accepts_contact_option_like_other_filtered_commands(self):
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

            exit_code, output = run_cli(["--db", str(db_path), "brief", "--contact", "群成员A"])

        self.assertEqual(0, exit_code)
        self.assertIn("# 联系人简报：群成员A", output)
        self.assertIn("- 来源群/会话：项目交流群（3）", output)
        self.assertNotIn("unrecognized arguments", output)

    def test_brief_evidence_for_group_speaker_ignores_later_mentions_by_other_people(self):
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
                image_path="/tmp/sunny-speaker.png",
            )
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "Alice\n"
                    "群成员A 上次提到的方案我看了一下，先放这里。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-27T09:00:00+08:00",
                image_path="/tmp/alice-mentions-sunny.png",
            )

            exit_code, output = run_cli(["--db", str(db_path), "brief", "群成员A"])

        self.assertEqual(0, exit_code)
        self.assertIn("# 联系人简报：群成员A", output)
        self.assertIn("- 采集时间：2026-05-26 22:21", output)
        self.assertIn("- 截图：/tmp/sunny-speaker.png", output)
        self.assertNotIn("/tmp/alice-mentions-sunny.png", output)

    def test_brief_matches_organization_hint_and_shows_low_priority_draft_by_default(self):
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

            exit_code, output = run_cli(["--db", str(db_path), "brief", "示例资本"])

        self.assertEqual(0, exit_code)
        self.assertIn("# 联系人简报：陈明 DANIEL", output)
        self.assertIn("- 身份线索：陈明, Daniel Chen", output)
        self.assertIn("- 机构/公司：示例资本", output)
        self.assertIn("- 动作：轻量问候", output)
        self.assertIn("- 跟进强度：低（没有强关系信号，可先不主动联系或仅轻量问候）", output)
        self.assertIn("草稿：陈明 DANIEL，之前看到你在示例资本的介绍", output)

    def test_brief_shows_low_priority_draft_for_group_speaker_shared_article(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "群成员A\n"
                    "最近看到一篇文章，挺有意思。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-26T22:21:20+08:00",
            )

            exit_code, output = run_cli(["--db", str(db_path), "brief", "--contact", "群成员A"])

        self.assertEqual(0, exit_code)
        self.assertIn("# 联系人简报：群成员A", output)
        self.assertIn("- 类型：群内联系人", output)
        self.assertIn("- 动作：轻量问候", output)
        self.assertIn("- 跟进强度：低（没有强关系信号，可先不主动联系或仅轻量问候）", output)
        self.assertIn("那篇文章", output)
        self.assertIn("值得看的内容", output)
        self.assertNotIn("最近有新进展吗", output)

    def test_brief_explains_when_low_priority_draft_is_filtered_by_min_score(self):
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

            exit_code, output = run_cli(["--db", str(db_path), "brief", "示例资本", "--min-score", "45"])

        self.assertEqual(0, exit_code)
        self.assertIn("# 联系人简报：陈明 DANIEL", output)
        self.assertIn("匹配「示例资本」的跟进建议低于当前阈值 45", output)
        self.assertIn("最高 20 分", output)
        self.assertIn("--min-score 0", output)
        self.assertNotIn("暂无匹配跟进建议。", output)

    def test_brief_shows_all_matches_when_query_is_ambiguous(self):
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

            exit_code, output = run_cli(["--db", str(db_path), "brief", "项目交流"])

        self.assertEqual(0, exit_code)
        self.assertIn("## 匹配到的联系人", output)
        self.assertIn("- 项目交流群（3）（群聊）", output)
        self.assertIn("- 群成员A（群内联系人，来源：项目交流群（3））", output)
        self.assertIn("- 建议对象：群成员A", output)

    def test_brief_evidence_for_group_query_follows_next_suggestion_target(self):
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
                image_path="/tmp/sunny-suggestion.png",
            )
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "Alice\n"
                    "这个资料先放群里，晚点再整理。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-27T09:00:00+08:00",
                image_path="/tmp/latest-group.png",
            )

            exit_code, output = run_cli(["--db", str(db_path), "brief", "项目交流"])

        self.assertEqual(0, exit_code)
        self.assertIn("- 建议对象：群成员A", output)
        self.assertIn("- 采集时间：2026-05-26 22:21", output)
        self.assertIn("- 截图：/tmp/sunny-suggestion.png", output)
        self.assertNotIn("/tmp/latest-group.png", output)

    def test_brief_empty_state_names_the_filter(self):
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

            exit_code, output = run_cli(["--db", str(db_path), "brief", "群成员A"])

        self.assertEqual(0, exit_code)
        self.assertIn("没有找到匹配「群成员A」的联系人。", output)
        self.assertNotIn("# 联系人简报", output)


if __name__ == "__main__":
    unittest.main()
