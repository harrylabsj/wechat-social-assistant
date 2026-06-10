import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from wsa.cli import main
from wsa.store import ingest_capture, init_db


class AuditCommandTests(unittest.TestCase):
    def test_audit_export_and_delete_commands(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            export_path = root / "exports" / "wsa.json"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="张三\n这个合作方案我还没回复。",
                contact_hint="张三",
                source="test",
                captured_at="2026-05-27T09:00:00+08:00",
            )

            audit_stdout = io.StringIO()
            with contextlib.redirect_stdout(audit_stdout):
                audit_exit = main(["--db", str(db_path), "audit"])

            with self.assertRaises(SystemExit):
                main(["--db", str(db_path), "export-data", "--out", str(export_path)])

            export_stdout = io.StringIO()
            with contextlib.redirect_stdout(export_stdout):
                export_exit = main(["--db", str(db_path), "export-data", "--out", str(export_path), "--yes"])

            dry_stdout = io.StringIO()
            with contextlib.redirect_stdout(dry_stdout):
                dry_exit = main(["--db", str(db_path), "delete-contact", "张三", "--dry-run"])

            delete_stdout = io.StringIO()
            with contextlib.redirect_stdout(delete_stdout):
                delete_exit = main(["--db", str(db_path), "delete-contact", "张三", "--yes"])
            export_exists = export_path.exists()

        self.assertEqual(0, audit_exit)
        self.assertIn("# 本地数据审计", audit_stdout.getvalue())
        self.assertEqual(0, export_exit)
        self.assertTrue(export_exists)
        self.assertIn("exported local data", export_stdout.getvalue())
        self.assertEqual(0, dry_exit)
        self.assertIn("dry-run", dry_stdout.getvalue())
        self.assertEqual(0, delete_exit)
        self.assertIn("deleted contact", delete_stdout.getvalue())
        self.assertIn("screenshots=0", delete_stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
