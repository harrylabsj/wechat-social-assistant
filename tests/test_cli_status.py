import tempfile
import unittest
from pathlib import Path

from wsa.cli import build_parser
from wsa.status import (
    build_status_report,
    detect_watch_processes,
    render_status_report,
    stop_watch_processes,
)
from wsa.store import connect, ingest_capture, init_db


AS_OF = "2026-05-28T12:00:00+08:00"


class StatusCommandTests(unittest.TestCase):
    def test_status_parser_defaults_log_file_next_to_database(self):
        parser = build_parser()
        args = parser.parse_args(["--db", "/tmp/wsa-test/social.db", "status"])

        self.assertEqual(Path("/tmp/wsa-test/watch.log"), args.log_file)

    def test_build_status_report_summarizes_database_files_and_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            captures_dir = root / "data" / "captures"
            captures_dir.mkdir(parents=True)
            image_path = captures_dir / "wechat-20260526-222119.png"
            image_path.write_bytes(b"not a real image")
            log_file = root / "data" / "watch.log"
            log_file.write_text(
                "\n".join(
                    [
                        "2026-05-26T22:21:20+08:00 app=微信 action=capture detail=ok via swift",
                        "2026-05-26T22:21:52+08:00 app=Codex action=skip detail=not target app via swift",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "群成员A\n"
                    "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。"
                ),
                contact_hint="项目交流群（3）",
                source="watch",
                captured_at="2026-05-26T22:21:31+08:00",
                image_path=str(image_path),
            )
            with connect(db_path) as conn:
                conn.execute("delete from capture_signals")
                conn.commit()

            report = build_status_report(db_path, log_file=log_file, captures_dir=captures_dir, as_of=AS_OF)
            rendered = render_status_report(report)

        self.assertEqual(1, report.capture_count)
        self.assertEqual(2, report.contact_count)
        self.assertEqual(2, report.profile_count)
        self.assertEqual(1, report.signal_count)
        self.assertEqual(1, report.screenshot_count)
        self.assertEqual("项目交流群（3）", report.latest_contact)
        self.assertIn("profiles: 2", rendered)
        self.assertIn("signals: 1", rendered)
        self.assertIn("top followup: 群成员A / 项目跟进 / 50分 / 中（有明确关系信号，适合跟进）", rendered)
        self.assertIn("latest: 2026-05-26 22:21 项目交流群（3）", rendered)
        self.assertNotIn("latest: 2026-05-26T22:21:31+08:00", rendered)
        self.assertIn("screenshots: 1", rendered)
        self.assertIn("last log: 2026-05-26T22:21:52+08:00 app=Codex action=skip", rendered)

    def test_status_counts_tif_screenshots(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            captures_dir = root / "data" / "captures"
            captures_dir.mkdir(parents=True)
            (captures_dir / "wechat-1.tif").write_bytes(b"tif")
            (captures_dir / "wechat-2.tiff").write_bytes(b"tiff")
            (captures_dir / "notes.txt").write_text("ignore", encoding="utf-8")
            init_db(db_path)

            report = build_status_report(db_path, captures_dir=captures_dir, process_rows=[])

        self.assertEqual(2, report.screenshot_count)

    def test_detect_watch_processes_finds_wsa_watch_and_ignores_current_process(self):
        rows = [
            "100 /usr/bin/python3 -m wsa.cli watch --interval 10",
            "101 /usr/bin/python3 -m wsa.cli status",
            "102 rg wsa.cli watch",
            "103 /usr/bin/python3 -m wsa.cli watch --interval 30",
        ]

        processes = detect_watch_processes(rows, current_pid=103)

        self.assertEqual((100,), processes)

    def test_detect_watch_processes_finds_console_script_watch(self):
        rows = [
            "100 /Users/me/.venv/bin/wsa --db data/social.db watch --interval 10",
            "101 /Users/me/.venv/bin/wsa --db data/social.db status",
            "102 pgrep -fl wsa watch",
        ]

        processes = detect_watch_processes(rows, current_pid=999)

        self.assertEqual((100,), processes)

    def test_status_report_renders_watch_running_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)

            running = build_status_report(
                db_path,
                process_rows=["321 /usr/bin/python3 -m wsa.cli watch --interval 10"],
            )
            stopped = build_status_report(db_path, process_rows=[])

        self.assertTrue(running.watch_running)
        self.assertFalse(stopped.watch_running)
        self.assertIn("watch: running (1 process)", render_status_report(running))
        self.assertIn("watch: stopped", render_status_report(stopped))

    def test_status_report_filters_watch_processes_by_selected_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            selected_db = root / "a" / "social.db"
            other_db = root / "b" / "social.db"
            init_db(selected_db)
            init_db(other_db)

            report = build_status_report(
                selected_db,
                process_rows=[f"321 /usr/bin/python3 -m wsa.cli --db {other_db} watch --interval 10"],
            )

        self.assertFalse(report.watch_running)

    def test_status_report_renders_quality_notes_for_limited_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="李四\n最近看到一篇文章，挺有意思。",
                contact_hint="李四",
                source="test",
                captured_at="2026-05-26T22:21:31+08:00",
            )

            report = build_status_report(db_path, process_rows=[], as_of=AS_OF)
            rendered = render_status_report(report)

        self.assertIn("quality: 采集样本较少（1 条），画像可能不完整", rendered)
        self.assertIn("暂未识别到关系信号，建议继续采集更多上下文", rendered)
        self.assertIn("自动截图未运行，分析只基于现有数据", rendered)

    def test_status_report_explains_when_only_low_priority_followups_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="李四\n最近看到一篇文章，挺有意思。",
                contact_hint="李四",
                source="test",
                captured_at="2026-05-26T22:21:31+08:00",
            )

            report = build_status_report(db_path, process_rows=[], as_of=AS_OF)
            rendered = render_status_report(report)

        self.assertIn(
            "top followup: 暂无 45 分以上建议；最高低分建议：李四 / 轻量问候 / 20分 / 低（没有强关系信号，可先不主动联系或仅轻量问候）；查看低分草稿：suggest --min-score 0",
            rendered,
        )
        self.assertNotIn("top followup: none\n", rendered)

    def test_stop_watch_processes_only_signals_detected_watch_processes(self):
        killed: list[tuple[int, int]] = []
        rows = [
            "100 /usr/bin/python3 -m wsa.cli watch --interval 10",
            "101 /usr/bin/python3 -m wsa.cli status",
            "102 rg wsa.cli watch",
        ]

        stopped = stop_watch_processes(
            process_rows=rows,
            current_pid=999,
            kill_fn=lambda pid, sig: killed.append((pid, sig)),
        )

        self.assertEqual((100,), stopped)
        self.assertEqual([(100, 15)], killed)

    def test_stop_watch_processes_filters_by_database_path(self):
        killed: list[tuple[int, int]] = []
        rows = [
            "100 /usr/bin/python3 -m wsa.cli --db /tmp/a/social.db watch --interval 10",
            "101 /usr/bin/python3 -m wsa.cli --db /tmp/b/social.db watch --interval 10",
        ]

        stopped = stop_watch_processes(
            process_rows=rows,
            current_pid=999,
            db_path=Path("/tmp/a/social.db"),
            kill_fn=lambda pid, sig: killed.append((pid, sig)),
        )

        self.assertEqual((100,), stopped)
        self.assertEqual([(100, 15)], killed)

    def test_stop_watch_processes_matches_default_watch_without_db_argument(self):
        killed: list[tuple[int, int]] = []
        rows = [
            "100 /usr/bin/python3 -m wsa.cli watch --mode screen",
            "101 /usr/bin/python3 -m wsa.cli --db /tmp/b/social.db watch --interval 10",
        ]

        stopped = stop_watch_processes(
            process_rows=rows,
            current_pid=999,
            db_path=Path("/tmp/a/social.db"),
            kill_fn=lambda pid, sig: killed.append((pid, sig)),
        )

        self.assertEqual((100,), stopped)
        self.assertEqual([(100, 15)], killed)

    def test_stop_watch_processes_dry_run_does_not_signal(self):
        killed: list[tuple[int, int]] = []

        stopped = stop_watch_processes(
            process_rows=["100 /usr/bin/python3 -m wsa.cli watch --interval 10"],
            dry_run=True,
            kill_fn=lambda pid, sig: killed.append((pid, sig)),
        )

        self.assertEqual((100,), stopped)
        self.assertEqual([], killed)


if __name__ == "__main__":
    unittest.main()
