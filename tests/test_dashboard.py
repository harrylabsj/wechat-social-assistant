import tempfile
import unittest
from pathlib import Path

from wsa.candidates import sync_relationship_candidates
from wsa.dashboard import build_relationship_dashboard, render_relationship_dashboard_markdown
from wsa.sources import import_relationship_sources
from wsa.store import ingest_capture, init_db


class RelationshipDashboardTests(unittest.TestCase):
    def test_builds_daily_operating_view_from_local_memory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            _seed_dashboard_data(root, db_path)

            dashboard = build_relationship_dashboard(
                db_path,
                as_of="2026-05-27T12:00:00+08:00",
                min_score=0,
            )
            markdown = render_relationship_dashboard_markdown(dashboard)

        self.assertEqual("2026-05-27T12:00:00+08:00", dashboard.as_of)
        self.assertTrue(any(item.name == "张三" for item in dashboard.priority_followups))
        self.assertTrue(any(item.name == "李四" for item in dashboard.cooling_contacts))
        self.assertTrue(any(item.name == "赵六" for item in dashboard.candidate_opportunities))
        self.assertTrue(any(item.name == "张三" for item in dashboard.open_commitments))
        self.assertTrue(any(item.name == "医疗AI路演群（6）" for item in dashboard.high_value_groups))
        self.assertTrue(any(item.name == "闲聊群（20）" for item in dashboard.noisy_groups))
        self.assertTrue(any(item.name == "陈明" for item in dashboard.source_updates))

        self.assertIn("# 关系驾驶舱", markdown)
        self.assertIn("## 优先联系", markdown)
        self.assertIn("## 降温关系", markdown)
        self.assertIn("## 新人机会", markdown)
        self.assertIn("## 待处理承诺", markdown)
        self.assertIn("## 高价值群聊", markdown)
        self.assertIn("## 噪音群聊", markdown)
        self.assertIn("张三", markdown)
        self.assertIn("陈明", markdown)


def _seed_dashboard_data(root: Path, db_path: Path) -> None:
    init_db(db_path)
    ingest_capture(
        db_path,
        raw_text="张三\n你上次提到的医疗AI合作方案还没回复我，方便这两天确认一下吗？",
        contact_hint="张三",
        source="test",
        captured_at="2026-05-27T09:00:00+08:00",
    )
    ingest_capture(
        db_path,
        raw_text="李四\n最近看到一篇文章，挺有意思。",
        contact_hint="李四",
        source="test",
        captured_at="2026-03-01T09:00:00+08:00",
    )
    ingest_capture(
        db_path,
        raw_text=(
            "医疗AI路演群（6）\n"
            "赵六\n"
            "我是未来医院的赵六，最近负责医疗AI落地，想看看是否有合作机会？\n"
            "王五\n"
            "谢谢分享，下周可以聊一下。"
        ),
        contact_hint="医疗AI路演群（6）",
        source="test",
        captured_at="2026-05-26T20:00:00+08:00",
    )
    ingest_capture(
        db_path,
        raw_text="闲聊群（20）\n群友A\n今天看到一个段子，哈哈哈。",
        contact_hint="闲聊群（20）",
        source="test",
        captured_at="2026-05-27T08:00:00+08:00",
    )
    source_file = root / "contacts.vcf"
    source_file.write_text(
        "\n".join(
            [
                "BEGIN:VCARD",
                "FN:陈明",
                "ORG:示例资本",
                "TITLE:投资人",
                "NOTE:校友会认识，关注医疗AI",
                "END:VCARD",
            ]
        ),
        encoding="utf-8",
    )
    import_relationship_sources(
        db_path,
        paths=[source_file],
        imported_at="2026-05-27T10:00:00+08:00",
    )
    sync_relationship_candidates(db_path, min_confidence=0)


if __name__ == "__main__":
    unittest.main()
