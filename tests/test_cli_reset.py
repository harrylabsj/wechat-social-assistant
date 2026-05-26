import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from wsa.cli import main
from wsa.store import connect, ingest_capture, init_db


class ResetCommandTests(unittest.TestCase):
    def test_reset_requires_yes_without_dry_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)

            with self.assertRaises(SystemExit) as raised:
                main(["--db", str(db_path), "reset"])

        self.assertEqual("Use --yes to clear database rows and screenshots, or --dry-run to preview.", str(raised.exception))

    def test_reset_dry_run_prints_counts_without_deleting(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            captures_dir = root / "data" / "captures"
            captures_dir.mkdir(parents=True)
            image = captures_dir / "wechat.png"
            image.write_bytes(b"png")
            ingest_capture(
                db_path,
                raw_text="王五\n下周方便聊聊吗？",
                contact_hint="王五",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
                image_path=str(image),
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["--db", str(db_path), "reset", "--dry-run"])

            with connect(db_path) as conn:
                capture_count = conn.execute("select count(*) from captures").fetchone()[0]

            output = stdout.getvalue()
            image_exists = image.exists()

        self.assertEqual(0, code)
        self.assertIn("dry-run", output)
        self.assertIn("captures=1", output)
        self.assertIn("screenshots=1", output)
        self.assertEqual(1, capture_count)
        self.assertTrue(image_exists)

    def test_reset_yes_clears_database_and_screenshots(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            captures_dir = root / "data" / "captures"
            captures_dir.mkdir(parents=True)
            image = captures_dir / "wechat.png"
            image.write_bytes(b"png")
            ingest_capture(
                db_path,
                raw_text="王五\n下周方便聊聊吗？",
                contact_hint="王五",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
                image_path=str(image),
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["--db", str(db_path), "reset", "--yes"])

            with connect(db_path) as conn:
                capture_count = conn.execute("select count(*) from captures").fetchone()[0]
                person_count = conn.execute("select count(*) from people").fetchone()[0]

            output = stdout.getvalue()
            image_exists = image.exists()

        self.assertEqual(0, code)
        self.assertIn("reset complete", output)
        self.assertEqual(0, capture_count)
        self.assertEqual(0, person_count)
        self.assertFalse(image_exists)


if __name__ == "__main__":
    unittest.main()
