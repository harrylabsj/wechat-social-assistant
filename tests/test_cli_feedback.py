import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from wsa.cli import main
from wsa.store import ingest_capture, init_db


class FeedbackCommandTests(unittest.TestCase):
    def test_feedback_command_records_auditable_feedback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_feedback_cli_data(db_path)

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "feedback",
                        "李四",
                        "too_pushy",
                        "--note",
                        "太主动，放轻一点",
                        "--created-at",
                        "2026-05-27T10:00:00+08:00",
                    ]
                )

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("recorded feedback", output)
        self.assertIn("contact=李四", output)
        self.assertIn("action=too_pushy", output)

    def test_feedback_list_command_outputs_recent_feedback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_feedback_cli_data(db_path)
            with contextlib.redirect_stdout(io.StringIO()):
                main(
                    [
                        "--db",
                        str(db_path),
                        "feedback",
                        "李四",
                        "snooze",
                        "--until",
                        "2026-05-30T09:00:00+08:00",
                        "--created-at",
                        "2026-05-27T10:00:00+08:00",
                    ]
                )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "feedback-list", "--contact", "李四"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("# 反馈记录", output)
        self.assertIn("| 李四 | snooze | 2026-05-30 09:00 |", output)


def _seed_feedback_cli_data(db_path: Path) -> None:
    init_db(db_path)
    ingest_capture(
        db_path,
        raw_text="李四\n下周方便聊聊你那个新项目吗？",
        contact_hint="李四",
        source="test",
        captured_at="2026-05-27T09:00:00+08:00",
    )


if __name__ == "__main__":
    unittest.main()
