import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wsa.cli import build_parser, main
from wsa.store import connect, ingest_capture, init_db


AS_OF = "2026-05-28T12:00:00+08:00"


class AnalyzeCommandTests(unittest.TestCase):
    def test_analyze_parser_defaults_reports_next_to_data_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                main(["--db", str(db_path), "analyze", "--limit", "1"])

            self.assertTrue((root / "reports" / "contact-profiles.md").exists())
            self.assertTrue((root / "reports" / "outreach.md").exists())

    def test_analyze_parser_defaults_reports_next_to_flat_database(self):
        parser = build_parser()
        db_path = Path("/tmp/wsa-flat/social.db")

        args = parser.parse_args(["--db", str(db_path), "analyze"])

        self.assertEqual(Path("/tmp/wsa-flat/reports/contact-profiles.md"), args.profiles_out)
        self.assertEqual(Path("/tmp/wsa-flat/reports/outreach.md"), args.suggestions_out)

    def test_analyze_writes_profiles_suggestions_and_prints_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            profiles_out = root / "reports" / "contact-profiles.md"
            suggestions_out = root / "reports" / "outreach.md"
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
            with connect(db_path) as conn:
                conn.execute("delete from capture_signals")
                conn.commit()

            stdout = io.StringIO()
            with patch("wsa.status._process_rows", return_value=[]), contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "analyze",
                        "--profiles-out",
                        str(profiles_out),
                        "--suggestions-out",
                        str(suggestions_out),
                        "--as-of",
                        AS_OF,
                    ]
                )

            output = stdout.getvalue()
            profiles_text = profiles_out.read_text(encoding="utf-8")
            suggestions_text = suggestions_out.read_text(encoding="utf-8")
            with connect(db_path) as conn:
                signal_count = conn.execute("select count(*) from capture_signals").fetchone()[0]

            self.assertEqual(0, exit_code)
            self.assertEqual(1, signal_count)
            self.assertTrue(profiles_out.exists())
            self.assertTrue(suggestions_out.exists())
            self.assertIn("采集：1", output)
            self.assertIn("联系人：2", output)
            self.assertIn("档案：2", output)
            self.assertIn("质量提示：采集样本较少（1 条），画像可能不完整；自动截图未运行，分析只基于现有数据", output)
            self.assertIn("跟进建议数：1", output)
            self.assertIn("首要跟进：群成员A / 项目跟进 / 50分 / 中（有明确关系信号，适合跟进）", output)
            self.assertIn("首条草稿：群成员A，上次你在「项目交流群（3）」里提到", output)
            self.assertIn("我这边可以继续补充。", output)
            self.assertNotIn("首条草稿：无", output)
            self.assertIn("自动截图：", output)
            self.assertIn("最近采集：2026-05-26 22:21 项目交流群（3）", output)
            self.assertNotIn("最近采集：2026-05-26T22:21:20+08:00", output)
            self.assertIn("联系人报告：", output)
            self.assertIn("跟进建议：", output)
            self.assertIn(
                "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。或者咱们打算往哪个方向做，我再着重研究一下。",
                profiles_text,
            )
            self.assertIn("- 关系信号：项目/合作", profiles_text)
            self.assertIn("# 社交跟进建议", suggestions_text)
            self.assertIn(
                "| 群成员A | 50 | 中（有明确关系信号，适合跟进） | 2026-05-26 22:21 | 项目跟进 |",
                suggestions_text,
            )
            self.assertIn("来自群：项目交流群（3）", suggestions_text)
            self.assertIn("群成员A，上次你在「项目交流群（3）」里提到", suggestions_text)
            self.assertNotIn("暂无需要跟进的联系人。", suggestions_text)
            self.assertNotIn("项目交流群（3） | 轻量问候", suggestions_text)

    def test_analyze_contact_filters_profiles_and_suggestions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            profiles_out = root / "reports" / "contact-profiles.md"
            suggestions_out = root / "reports" / "outreach.md"
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
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "analyze",
                        "--contact",
                        "项目交流",
                        "--profiles-out",
                        str(profiles_out),
                        "--suggestions-out",
                        str(suggestions_out),
                        "--as-of",
                        AS_OF,
                    ]
                )

            output = stdout.getvalue()
            profiles_text = profiles_out.read_text(encoding="utf-8")
            suggestions_text = suggestions_out.read_text(encoding="utf-8")

        self.assertEqual(0, exit_code)
        self.assertIn("过滤：项目交流", output)
        self.assertIn("匹配联系人：2", output)
        self.assertIn("匹配最近出现：2026-05-26 22:21 群成员A", output)
        self.assertIn("档案：2", output)
        self.assertIn("跟进建议数：1", output)
        self.assertIn("首要跟进：群成员A / 项目跟进 / 50分 / 中（有明确关系信号，适合跟进）", output)
        self.assertIn("## 群成员A", profiles_text)
        self.assertIn("## 项目交流群（3）", profiles_text)
        self.assertNotIn("## 赵六", profiles_text)
        self.assertIn("| 群成员A |", suggestions_text)
        self.assertNotIn("| 赵六 |", suggestions_text)

    def test_analyze_contact_searches_all_profiles_before_default_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            profiles_out = root / "reports" / "contact-profiles.md"
            suggestions_out = root / "reports" / "outreach.md"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="李四\n最近看到一篇文章，挺有意思。",
                contact_hint="李四",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
            )
            for index in range(21):
                ingest_capture(
                    db_path,
                    raw_text=f"近期联系人{index:02d}\n下周约饭吗？",
                    contact_hint=f"近期联系人{index:02d}",
                    source="test",
                    captured_at=f"2026-05-26T22:{index:02d}:00+08:00",
                )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "analyze",
                        "--contact",
                        "李四",
                        "--profiles-out",
                        str(profiles_out),
                        "--suggestions-out",
                        str(suggestions_out),
                        "--as-of",
                        AS_OF,
                    ]
                )

            output = stdout.getvalue()
            profiles_text = profiles_out.read_text(encoding="utf-8")

        self.assertEqual(0, exit_code)
        self.assertIn("过滤：李四", output)
        self.assertIn("档案：1", output)
        self.assertIn("## 李四", profiles_text)
        self.assertIn("最近看到一篇文章，挺有意思。", profiles_text)
        self.assertNotIn("没有找到匹配「李四」的联系人档案。", profiles_text)

    def test_analyze_contact_empty_reports_name_the_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            profiles_out = root / "reports" / "contact-profiles.md"
            suggestions_out = root / "reports" / "outreach.md"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="赵六\n上次的问题你还没回复我，方便的时候看下。",
                contact_hint="赵六",
                source="test",
                captured_at="2026-05-26T22:20:20+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "analyze",
                        "--contact",
                        "群成员A",
                        "--profiles-out",
                        str(profiles_out),
                        "--suggestions-out",
                        str(suggestions_out),
                        "--as-of",
                        AS_OF,
                    ]
                )

            output = stdout.getvalue()
            profiles_text = profiles_out.read_text(encoding="utf-8")
            suggestions_text = suggestions_out.read_text(encoding="utf-8")

        self.assertEqual(0, exit_code)
        self.assertIn("过滤：群成员A", output)
        self.assertIn("匹配联系人：0", output)
        self.assertIn("匹配最近出现：无", output)
        self.assertIn("档案：0", output)
        self.assertIn("跟进建议数：0", output)
        self.assertIn("首要跟进：无", output)
        self.assertIn("没有找到匹配「群成员A」的联系人档案。", profiles_text)
        self.assertIn("没有找到匹配「群成员A」的跟进建议。", suggestions_text)
        self.assertNotIn("暂无联系人档案。", profiles_text)
        self.assertNotIn("暂无需要跟进的联系人。", suggestions_text)

    def test_analyze_contact_empty_suggestions_mentions_threshold_when_low_score_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            profiles_out = root / "reports" / "contact-profiles.md"
            suggestions_out = root / "reports" / "outreach.md"
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
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "analyze",
                        "--contact",
                        "李四",
                        "--profiles-out",
                        str(profiles_out),
                        "--suggestions-out",
                        str(suggestions_out),
                        "--as-of",
                        AS_OF,
                    ]
                )

            output = stdout.getvalue()
            suggestions_text = suggestions_out.read_text(encoding="utf-8")

        self.assertEqual(0, exit_code)
        self.assertIn("跟进建议数：0", output)
        self.assertIn("阈值提示：匹配「李四」的跟进建议低于当前阈值 45", output)
        self.assertIn("匹配「李四」的跟进建议低于当前阈值 45", suggestions_text)
        self.assertIn("最高 20 分", suggestions_text)
        self.assertIn("--min-score 0", suggestions_text)
        self.assertNotIn("没有找到匹配「李四」的跟进建议。", suggestions_text)

    def test_analyze_backfills_group_speakers_into_people(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            init_db(db_path)
            with connect(db_path) as conn:
                conn.execute(
                    """
                    insert into people
                    (name, aliases_json, notes, created_at, updated_at, last_interaction_at)
                    values (?, '[]', '', ?, ?, ?)
                    """,
                    (
                        "项目交流群（3）",
                        "2026-05-26T22:21:20+08:00",
                        "2026-05-26T22:21:20+08:00",
                        "2026-05-26T22:21:20+08:00",
                    ),
                )
                person_id = conn.execute("select id from people where name = ?", ("项目交流群（3）",)).fetchone()[0]
                conn.execute(
                    """
                    insert into captures
                    (person_id, captured_at, source, raw_text, clean_text, text_hash, image_path, created_at)
                    values (?, ?, 'legacy', ?, ?, 'legacy-hash', null, ?)
                    """,
                    (
                        person_id,
                        "2026-05-26T22:21:20+08:00",
                        "项目交流群（3）\n群成员A\n可以参考一下这家",
                        "群成员A\n可以参考一下这家",
                        "2026-05-26T22:21:20+08:00",
                    ),
                )
                conn.commit()

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "analyze"])

            with connect(db_path) as conn:
                people = conn.execute(
                    "select name, last_interaction_at from people order by name"
                ).fetchall()

        self.assertEqual(0, exit_code)
        self.assertEqual(
            [
                ("群成员A", "2026-05-26T22:21:20+08:00"),
                ("项目交流群（3）", "2026-05-26T22:21:20+08:00"),
            ],
            [(row["name"], row["last_interaction_at"]) for row in people],
        )


if __name__ == "__main__":
    unittest.main()
