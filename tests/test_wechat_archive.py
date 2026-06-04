import tempfile
import unittest
from pathlib import Path

from wsa.sources import list_relationship_sources
from wsa.store import init_db
from wsa.wechat_archive import import_wechat_archive_manifest


class WeChatArchiveImportTests(unittest.TestCase):
    def test_imports_safe_manifest_rows_as_relationship_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            init_db(db_path)
            manifest = _write_manifest(root)

            dry_run = import_wechat_archive_manifest(
                db_path,
                manifest_path=manifest,
                known_contacts=["张三", "李四"],
                dry_run=True,
                min_score=0,
                include_unmatched=True,
                imported_at="2026-06-01T10:00:00+08:00",
            )
            before = list_relationship_sources(db_path)
            result = import_wechat_archive_manifest(
                db_path,
                manifest_path=manifest,
                known_contacts=["张三", "李四"],
                min_score=0,
                include_unmatched=True,
                imported_at="2026-06-01T10:00:00+08:00",
            )
            records = list_relationship_sources(db_path, source_type="wechat_archive")

        self.assertEqual(0, dry_run.imported_count)
        self.assertEqual([], before)
        self.assertEqual(2, dry_run.parsed_count)
        self.assertEqual(2, result.imported_count)
        self.assertEqual(1, result.skipped_sensitive_count)
        self.assertEqual({"张三", "项目线索：新能源物流"}, {record.person_name for record in records})
        self.assertTrue(any(record.fields.get("matched_contact") == "张三" for record in records))
        self.assertTrue(all(record.fields.get("sensitivity") == "normal" for record in records))

    def test_can_include_sensitive_rows_explicitly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            init_db(db_path)
            manifest = _write_manifest(root)

            result = import_wechat_archive_manifest(
                db_path,
                manifest_path=manifest,
                known_contacts=["李四"],
                min_score=0,
                include_unmatched=False,
                include_sensitive=True,
                imported_at="2026-06-01T10:00:00+08:00",
            )
            records = list_relationship_sources(db_path, person_name="李四", source_type="wechat_archive")

        self.assertEqual(1, result.imported_count)
        self.assertEqual(1, len(records))
        self.assertEqual("high", records[0].fields.get("sensitivity"))


def _write_manifest(root: Path) -> Path:
    manifest = root / "manifest-all.tsv"
    manifest.write_text(
        "\n".join(
            [
                "size_bytes\tsize_mib\tmodified\textension\tcategory\tmonth\tfilename\tsource_path\tarchive_path\tcopy_status",
                "1200\t0.01\t2026-05-20 09:00:00\tpdf\tfile\t2026-05\t张三合作方案.pdf\t/src/a\t/archive/a\tcopied",
                "900\t0.01\t2026-05-21 09:00:00\tpdf\tfile\t2026-05\t李四简历.pdf\t/src/b\t/archive/b\tcopied",
                "800\t0.01\t2026-05-22 09:00:00\tpptx\tfile\t2026-05\t新能源物流项目路演.pptx\t/src/c\t/archive/c\tcopied",
            ]
        ),
        encoding="utf-8",
    )
    return manifest


if __name__ == "__main__":
    unittest.main()
