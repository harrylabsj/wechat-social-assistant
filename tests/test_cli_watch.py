import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from wsa.cli import WatchLogState, _append_watch_log, _should_emit_watch_log, _watch_log_line, build_parser, cmd_watch, main


class WatchLogTests(unittest.TestCase):
    def test_watch_parser_defaults_log_file_next_to_database(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "--db",
                "/tmp/wsa-test/social.db",
                "watch",
            ]
        )

        self.assertEqual(Path("/tmp/wsa-test/watch.log"), args.log_file)

    def test_stop_watch_parser_supports_dry_run_alias(self):
        parser = build_parser()
        args = parser.parse_args(["stop", "--dry-run"])

        self.assertEqual("stop", args.command)
        self.assertTrue(args.dry_run)

    def test_stop_watch_command_passes_selected_database_to_process_filter(self):
        with patch("wsa.cli.stop_watch_processes", return_value=()) as stop_watch:
            exit_code = main(["--db", "/tmp/a/social.db", "stop-watch", "--dry-run"])

        self.assertEqual(0, exit_code)
        stop_watch.assert_called_once_with(dry_run=True, db_path=Path("/tmp/a/social.db"))

    def test_watch_log_line_includes_time_app_action_and_detail(self):
        line = _watch_log_line(
            "2026-05-26T20:00:00+08:00",
            app_name="Cursor",
            action="skip",
            detail="not target app",
        )

        self.assertEqual(
            "2026-05-26T20:00:00+08:00 app=Cursor action=skip detail=not target app",
            line,
        )

    def test_append_watch_log_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "logs" / "watch.log"

            _append_watch_log(path, "first line")
            _append_watch_log(path, "second line")

            self.assertEqual("first line\nsecond line\n", path.read_text(encoding="utf-8"))

    def test_repeated_skip_logs_are_throttled_with_heartbeat(self):
        state = WatchLogState()
        emitted = [
            _should_emit_watch_log(
                state,
                action="skip",
                app_name="loginwindow",
                detail="not target app via swift",
                quiet_skip_every=3,
            )
            for _ in range(7)
        ]

        self.assertEqual([True, False, False, True, False, False, True], emitted)

    def test_capture_logs_reset_skip_throttle(self):
        state = WatchLogState()
        self.assertTrue(
            _should_emit_watch_log(
                state,
                action="skip",
                app_name="loginwindow",
                detail="not target app via swift",
                quiet_skip_every=10,
            )
        )
        self.assertFalse(
            _should_emit_watch_log(
                state,
                action="skip",
                app_name="loginwindow",
                detail="not target app via swift",
                quiet_skip_every=10,
            )
        )
        self.assertTrue(
            _should_emit_watch_log(
                state,
                action="capture",
                app_name="微信",
                detail="ok via swift",
                quiet_skip_every=10,
            )
        )
        self.assertTrue(
            _should_emit_watch_log(
                state,
                action="skip",
                app_name="loginwindow",
                detail="not target app via swift",
                quiet_skip_every=10,
            )
        )

    def test_watch_capture_log_includes_insert_status_and_signals(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            log_file = root / "data" / "watch.log"
            image_path = root / "data" / "captures" / "fixed.png"
            args = build_parser().parse_args(
                [
                    "--db",
                    str(db_path),
                    "watch",
                    "--contact",
                    "李四",
                    "--interval",
                    "5",
                    "--log-file",
                    str(log_file),
                ]
            )

            def fake_capture(path, *_args, **_kwargs):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"watch screenshot")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch(
                    "wsa.cli.frontmost_app_status",
                    return_value=SimpleNamespace(name="微信", method="swift", detail="ok"),
                ),
                patch("wsa.cli.next_capture_path", return_value=image_path),
                patch("wsa.cli.capture_screenshot", side_effect=fake_capture),
                patch("wsa.cli.ocr_image", return_value="李四\n最近看到一篇文章，挺有意思。"),
                patch("wsa.cli.time.sleep", side_effect=KeyboardInterrupt),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
                self.assertRaises(KeyboardInterrupt),
            ):
                cmd_watch(args)

            log_text = log_file.read_text(encoding="utf-8")

        self.assertIn("action=capture", log_text)
        self.assertIn("detail=inserted capture=1 contact=李四", log_text)
        self.assertIn("signals=无", log_text)
        self.assertIn(f"image={image_path}", log_text)
        self.assertIn("via swift", log_text)
        self.assertNotIn("detail=ok via swift", log_text)


if __name__ == "__main__":
    unittest.main()
