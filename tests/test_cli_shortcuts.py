import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wsa.cli import CaptureOutcome, build_parser, main


class ShortcutCommandTests(unittest.TestCase):
    def test_dashboard_storage_and_watch_shortcuts_build_with_callbacks(self):
        parser = build_parser()

        for argv, command, callback in (
            (["ui", "--no-browser"], "ui", "cmd_ui"),
            (["web", "--no-browser"], "web", "cmd_ui"),
            (["captures-dir"], "captures-dir", "cmd_captures_dir"),
            (["capture-dir"], "capture-dir", "cmd_captures_dir"),
            (["stop-watch"], "stop-watch", "cmd_stop_watch"),
        ):
            args = parser.parse_args(argv)
            self.assertEqual(command, args.command)
            self.assertEqual(callback, args.func.__name__)

    def test_quick_capture_uses_hotkey_friendly_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            stdout = io.StringIO()

            with (
                patch(
                    "wsa.cli._capture_once",
                    return_value=CaptureOutcome(
                        output_line="inserted capture=1 contact=张三 person=1 signals=无 image=/tmp/fixed.png",
                        log_detail="inserted capture=1 contact=张三",
                    ),
                ) as capture_once,
                contextlib.redirect_stdout(stdout),
            ):
                exit_code = main(["--db", str(db_path), "quick-capture"])

        self.assertEqual(0, exit_code)
        self.assertIn("inserted capture=1 contact=张三", stdout.getvalue())
        args = capture_once.call_args.args[0]
        self.assertEqual(db_path, args.db)
        self.assertEqual("window", args.mode)
        self.assertEqual("none", args.crop_preset)
        self.assertEqual("hotkey", args.source)
        self.assertIsNone(args.contact)

    def test_watch_interval_persists_setting_next_to_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                set_exit = main(["--db", str(db_path), "watch-interval", "12"])
                show_exit = main(["--db", str(db_path), "watch-interval"])

            settings = json.loads((db_path.parent / "settings.json").read_text(encoding="utf-8"))

        self.assertEqual(0, set_exit)
        self.assertEqual(0, show_exit)
        self.assertEqual({"watch_interval_seconds": 12}, settings)
        self.assertEqual(
            "watch_interval_seconds=12 settings=data/settings.json\n"
            "watch_interval_seconds=12 settings=data/settings.json\n",
            stdout.getvalue(),
        )

    def test_watch_interval_ignores_invalid_saved_interval(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            settings_path = db_path.parent / "settings.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text('{"watch_interval_seconds": 2}\n', encoding="utf-8")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "watch-interval"])

        self.assertEqual(0, exit_code)
        self.assertEqual("watch_interval_seconds=60 settings=data/settings.json\n", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
