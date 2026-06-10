import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from wsa.cli import main
from wsa.sources import list_relationship_sources
from wsa.store import init_db


class SourceCommandTests(unittest.TestCase):
    def test_import_source_requires_confirmation_and_lists_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            init_db(db_path)
            source_file = root / "contacts.vcf"
            source_file.write_text(
                "\n".join(
                    [
                        "BEGIN:VCARD",
                        "FN:赵六",
                        "ORG:未来医院",
                        "TITLE:医务部主任",
                        "END:VCARD",
                    ]
                ),
                encoding="utf-8",
            )

            dry_stdout = io.StringIO()
            with contextlib.redirect_stdout(dry_stdout):
                dry_exit = main(["--db", str(db_path), "import-source", str(source_file), "--dry-run"])
            self.assertEqual([], list_relationship_sources(db_path))

            with self.assertRaises(SystemExit):
                main(["--db", str(db_path), "import-source", str(source_file)])

            import_stdout = io.StringIO()
            with contextlib.redirect_stdout(import_stdout):
                import_exit = main(
                    [
                        "--db",
                        str(db_path),
                        "import-source",
                        str(source_file),
                        "--yes",
                        "--imported-at",
                        "2026-05-27T12:00:00+08:00",
                    ]
                )

            list_stdout = io.StringIO()
            with contextlib.redirect_stdout(list_stdout):
                list_exit = main(["--db", str(db_path), "sources", "--contact", "赵六"])

        self.assertEqual(0, dry_exit)
        self.assertIn("dry-run", dry_stdout.getvalue())
        self.assertEqual(0, import_exit)
        self.assertIn("imported relationship sources", import_stdout.getvalue())
        self.assertEqual(0, list_exit)
        self.assertIn("# 多入口关系来源", list_stdout.getvalue())
        self.assertIn("未来医院", list_stdout.getvalue())

    def test_import_source_directory_reports_skipped_binary_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            init_db(db_path)
            source_dir = root / "sources"
            source_dir.mkdir()
            (source_dir / "meeting.md").write_text(
                "# 项目会\n\n日期：2026-05-29\n参会人：张三\n\n讨论项目计划。",
                encoding="utf-8",
            )
            (source_dir / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "import-source", str(source_dir), "--dry-run"])

        self.assertEqual(0, exit_code)
        self.assertIn("dry-run: scanned=1 parsed=1 imported=0 duplicates=0 skipped=1", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
