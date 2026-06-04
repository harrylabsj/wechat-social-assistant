import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from wsa.cli import main
from wsa.sources import list_relationship_sources
from wsa.store import ingest_capture, init_db


class CockpitCommandTests(unittest.TestCase):
    def test_cockpit_dry_run_prints_without_default_report_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            init_db(db_path)
            vault = root / "Hbrain"
            (vault / "社交圈" / "人脉").mkdir(parents=True)
            manifest = root / "manifest-all.tsv"
            manifest.write_text(
                "size_bytes\tsize_mib\tmodified\textension\tcategory\tmonth\tfilename\tsource_path\tarchive_path\tcopy_status\n",
                encoding="utf-8",
            )

            stdout = io.StringIO()
            old_cwd = Path.cwd()
            os.chdir(root)
            try:
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "--db",
                            str(db_path),
                            "cockpit",
                            "--vault",
                            str(vault),
                            "--wechat-manifest",
                            str(manifest),
                            "--dry-run",
                        ]
                    )
            finally:
                os.chdir(old_cwd)

            default_out = root / "reports" / "relationship-cockpit.md"

        self.assertEqual(0, exit_code)
        self.assertIn("# 关系跟进驾驶舱", stdout.getvalue())
        self.assertNotIn("wrote", stdout.getvalue())
        self.assertFalse(default_out.exists())

    def test_cockpit_imports_sources_and_writes_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="张三\n上次合作方案可以这周继续推进。",
                contact_hint="张三",
                source="test",
                captured_at="2026-06-01T09:00:00+08:00",
            )
            vault = root / "Hbrain"
            people_dir = vault / "社交圈" / "人脉"
            people_dir.mkdir(parents=True)
            (people_dir / "张三.md").write_text(
                "# 张三\n\n## 手工补充\n- 公司：示例资本\n- 职位/角色：投资人\n- 认识场景：路演\n",
                encoding="utf-8",
            )
            manifest = root / "manifest-all.tsv"
            manifest.write_text(
                "\n".join(
                    [
                        "size_bytes\tsize_mib\tmodified\textension\tcategory\tmonth\tfilename\tsource_path\tarchive_path\tcopy_status",
                        "1200\t0.01\t2026-06-01 09:30:00\tpdf\tfile\t2026-06\t张三合作方案.pdf\t/src/a\t/archive/a\tcopied",
                    ]
                ),
                encoding="utf-8",
            )
            out = root / "reports" / "relationship-cockpit.md"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "cockpit",
                        "--vault",
                        str(vault),
                        "--wechat-manifest",
                        str(manifest),
                        "--out",
                        str(out),
                        "--yes",
                        "--min-score",
                        "0",
                        "--archive-min-score",
                        "0",
                        "--imported-at",
                        "2026-06-01T10:00:00+08:00",
                    ]
                )
            records = list_relationship_sources(db_path, source_type="wechat_archive")
            report = out.read_text(encoding="utf-8")

        self.assertEqual(0, exit_code)
        self.assertIn("wrote", stdout.getvalue())
        self.assertEqual(1, len(records))
        self.assertIn("# 关系跟进驾驶舱", report)
        self.assertIn("微信归档文件线索导入：1", report)
        self.assertIn("张三", report)


if __name__ == "__main__":
    unittest.main()
