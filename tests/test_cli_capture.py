import contextlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wsa.cli import main


class CaptureCommandTests(unittest.TestCase):
    def test_capture_prints_person_and_chinese_signal_labels(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            image_path = root / "data" / "captures" / "fixed.png"

            stdout = io.StringIO()
            with (
                patch("wsa.cli.next_capture_path", return_value=image_path),
                patch("wsa.cli.capture_screenshot"),
                patch(
                    "wsa.cli.ocr_image",
                    return_value="王志平\n智能客服项目本周推出还有哪些工作？我还需要提供哪些？",
                ),
                contextlib.redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "capture",
                        "--contact",
                        "王志平",
                        "--mode",
                        "screen",
                    ]
                )

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("contact=王志平", output)
        self.assertIn("person=1", output)
        self.assertIn("signals=项目/合作,问题", output)
        self.assertNotIn("signals=project,question", output)

    def test_capture_removes_new_image_when_ocr_text_is_duplicate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            first_image = root / "data" / "captures" / "first.png"
            second_image = root / "data" / "captures" / "second.png"

            def fake_capture(path, *_args, **_kwargs):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"duplicate screenshot")

            stdout = io.StringIO()
            with (
                patch("wsa.cli.next_capture_path", side_effect=[first_image, second_image]),
                patch("wsa.cli.capture_screenshot", side_effect=fake_capture),
                patch("wsa.cli.ocr_image", return_value="李四\n最近看到一篇文章，挺有意思。"),
                contextlib.redirect_stdout(stdout),
            ):
                first_exit = main(["--db", str(db_path), "capture", "--contact", "李四"])
                second_exit = main(["--db", str(db_path), "capture", "--contact", "李四"])

            output = stdout.getvalue()
            self.assertEqual(0, first_exit)
            self.assertEqual(0, second_exit)
            self.assertTrue(first_image.exists())
            self.assertFalse(second_image.exists())
            self.assertIn("inserted capture=", output)
            self.assertIn("duplicate capture=", output)
            self.assertIn(f"duplicate_image_removed={second_image}", output)

    def test_capture_attaches_image_when_duplicate_manual_record_has_no_image(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            image_path = root / "data" / "captures" / "manual-duplicate.png"

            with contextlib.redirect_stdout(io.StringIO()):
                main(
                    [
                        "--db",
                        str(db_path),
                        "ingest",
                        "--contact",
                        "李四",
                        "--text",
                        "最近看到一篇文章，挺有意思。",
                        "--source",
                        "manual",
                    ]
                )

            def fake_capture(path, *_args, **_kwargs):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"manual duplicate screenshot")

            stdout = io.StringIO()
            with (
                patch("wsa.cli.next_capture_path", return_value=image_path),
                patch("wsa.cli.capture_screenshot", side_effect=fake_capture),
                patch("wsa.cli.ocr_image", return_value="李四\n最近看到一篇文章，挺有意思。"),
                patch("wsa.cli.now_iso", return_value="2026-05-27T10:00:00+08:00"),
                contextlib.redirect_stdout(stdout),
            ):
                exit_code = main(["--db", str(db_path), "capture", "--contact", "李四", "--source", "ocr"])

            output = stdout.getvalue()
            with contextlib.closing(sqlite3.connect(db_path)) as conn:
                stored = conn.execute("select image_path, source, captured_at from captures").fetchone()

            self.assertEqual(0, exit_code)
            self.assertTrue(image_path.exists())
            self.assertEqual(str(image_path), stored[0])
            self.assertEqual("ocr", stored[1])
            self.assertEqual("2026-05-27T10:00:00+08:00", stored[2])
            self.assertIn("duplicate capture=", output)
            self.assertIn(f"image_attached={image_path}", output)
            self.assertNotIn("duplicate_image_removed=", output)

    def test_manual_capture_keeps_screenshot_when_ocr_text_is_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            image_path = root / "data" / "captures" / "empty.png"

            def fake_capture(path, *_args, **_kwargs):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"empty screenshot")

            stderr = io.StringIO()
            with (
                patch("wsa.cli.next_capture_path", return_value=image_path),
                patch("wsa.cli.capture_screenshot", side_effect=fake_capture),
                patch("wsa.cli.ocr_image", return_value=" \n\t\n"),
                contextlib.redirect_stderr(stderr),
            ):
                exit_code = main(["--db", str(db_path), "capture", "--contact", "李四"])
            image_exists_after_capture = image_path.exists()

        self.assertEqual(2, exit_code)
        self.assertTrue(image_exists_after_capture)
        self.assertIn("ingest error: empty capture text", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
