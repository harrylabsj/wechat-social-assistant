import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from wsa.cli import main
from wsa.enrichment import list_contact_enrichments
from wsa.store import ingest_capture, init_db


class ObsidianImportCommandTests(unittest.TestCase):
    def test_import_obsidian_requires_yes_unless_dry_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            vault = root / "Obsidian Vault"
            _seed_import_data(db_path)
            main(["--db", str(db_path), "export-obsidian", "--vault", str(vault), "--date", "2026-05-27"])
            contact_path = vault / "社交圈" / "人脉" / "李四.md"
            contact_path.write_text(
                contact_path.read_text(encoding="utf-8")
                + "\n## 手工补充\n- 公司：北大国发院\n- 职位/角色：医疗AI研究员\n",
                encoding="utf-8",
            )

            dry_stdout = io.StringIO()
            with contextlib.redirect_stdout(dry_stdout):
                dry_exit = main(["--db", str(db_path), "import-obsidian", "--vault", str(vault), "--dry-run"])
            self.assertEqual([], list_contact_enrichments(db_path, person_name="李四"))

            with self.assertRaises(SystemExit):
                main(["--db", str(db_path), "import-obsidian", "--vault", str(vault)])

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "import-obsidian",
                        "--vault",
                        str(vault),
                        "--yes",
                        "--imported-at",
                        "2026-05-27T12:00:00+08:00",
                    ]
                )
            enrichments = list_contact_enrichments(db_path, person_name="李四")

        self.assertEqual(0, dry_exit)
        self.assertIn("dry-run", dry_stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertIn("imported obsidian enrichments", stdout.getvalue())
        self.assertEqual("北大国发院", enrichments[0].fields["company"])

    def test_weekly_report_command_outputs_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            _seed_import_data(db_path)

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "weekly-report", "--date", "2026-05-27", "--min-score", "0"])

        self.assertEqual(0, exit_code)
        self.assertIn("# 社交圈周报 2026-W22", stdout.getvalue())
        self.assertIn("## 本周应主动联系", stdout.getvalue())


def _seed_import_data(db_path: Path) -> None:
    init_db(db_path)
    ingest_capture(
        db_path,
        raw_text="李四\n下周方便聊聊医疗AI项目吗？",
        contact_hint="李四",
        source="test",
        captured_at="2026-05-27T09:00:00+08:00",
    )


if __name__ == "__main__":
    unittest.main()
