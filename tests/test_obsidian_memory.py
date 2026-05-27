import tempfile
import unittest
from pathlib import Path

from wsa.obsidian_memory import (
    import_obsidian_enrichments,
    list_contact_enrichments,
    parse_obsidian_contact_file,
)
from wsa.store import ingest_capture, init_db
from wsa.cli import main


class ObsidianMemoryTests(unittest.TestCase):
    def test_imports_manual_contact_enrichment_from_obsidian_and_export_reuses_it(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            vault = root / "Obsidian Vault"
            _seed_obsidian_memory_data(db_path)

            self.assertEqual(0, main(["--db", str(db_path), "export-obsidian", "--vault", str(vault), "--date", "2026-05-27"]))
            contact_path = vault / "社交圈" / "人脉" / "张三.md"
            exported_before = contact_path.read_text(encoding="utf-8")
            self.assertIn("## 手工补充", exported_before)
            self.assertIn("- 公司：", exported_before)

            contact_path.write_text(
                exported_before
                + "\n## 手工补充\n"
                + "- 公司：星火科技\n"
                + "- 职位/角色：创始人\n"
                + "- 认识场景：AI路演群会后交流\n"
                + "- 标签：医疗AI, 创业\n"
                + "- 备注：对医疗场景合作感兴趣\n"
                + "- 下次跟进：约15分钟聊医疗AI落地\n",
                encoding="utf-8",
            )

            parsed = parse_obsidian_contact_file(contact_path)
            result = import_obsidian_enrichments(
                db_path,
                vault=vault,
                imported_at="2026-05-27T12:00:00+08:00",
            )
            enrichments = list_contact_enrichments(db_path, person_name="张三")
            self.assertEqual(0, main(["--db", str(db_path), "export-obsidian", "--vault", str(vault), "--date", "2026-05-27"]))
            exported_after = contact_path.read_text(encoding="utf-8")
            report_text = (vault / "社交圈" / "分析报告" / "2026-05-27.md").read_text(encoding="utf-8")
            weekly_text = (vault / "社交圈" / "分析报告" / "2026-W22.md").read_text(encoding="utf-8")

        self.assertEqual("张三", parsed.person_name)
        self.assertEqual("星火科技", parsed.fields["company"])
        self.assertEqual(1, result.imported_count)
        self.assertEqual("星火科技", enrichments[0].fields["company"])
        self.assertIn("- 公司：星火科技", exported_after)
        self.assertIn("- 职位/角色：创始人", exported_after)
        self.assertNotIn("缺少身份/机构线索", exported_after)
        self.assertIn("### 手工补充的人脉", report_text)
        self.assertIn("张三：星火科技 / 创始人 / AI路演群会后交流", report_text)
        self.assertIn("# 社交圈周报 2026-W22", weekly_text)
        self.assertIn("## 本周手工补充", weekly_text)
        self.assertIn("张三：星火科技 / 创始人", weekly_text)


def _seed_obsidian_memory_data(db_path: Path) -> None:
    init_db(db_path)
    ingest_capture(
        db_path,
        raw_text=(
            "AI路演群（12）\n"
            "张三\n"
            "最近在做AI社交助手，想找医疗场景合作伙伴。"
        ),
        contact_hint="AI路演群（12）",
        source="test",
        captured_at="2026-05-27T09:00:00+08:00",
    )


if __name__ == "__main__":
    unittest.main()
