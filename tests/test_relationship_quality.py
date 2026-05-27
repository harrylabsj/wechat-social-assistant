import tempfile
import unittest
from pathlib import Path

from wsa.relationship_quality import build_relationship_quality_cards, render_relationship_quality_markdown
from wsa.store import ingest_capture, init_db


class RelationshipQualityTests(unittest.TestCase):
    def test_quality_cards_explain_scores_with_local_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_quality_data(db_path)

            cards = build_relationship_quality_cards(
                db_path,
                as_of="2026-05-27T12:00:00+08:00",
                min_suggestion_score=0,
            )

        by_name = {card.name: card for card in cards}
        self.assertIn("群成员A", by_name)
        card = by_name["群成员A"]

        self.assertEqual("speaker", card.kind)
        self.assertGreaterEqual(card.overall.score, 60)
        self.assertGreaterEqual(card.relationship_strength.score, 60)
        self.assertGreaterEqual(card.recency.score, 80)
        self.assertGreaterEqual(card.reciprocity.score, 35)
        self.assertIn("项目/合作", card.context_tags)
        self.assertIn("来源：项目交流群（3）", card.context_tags)
        self.assertIn("仅群聊上下文，主动联系前需要保持克制", card.risk_flags)
        self.assertIn("缺少私聊互动证据", card.information_gaps)
        self.assertEqual("项目跟进", card.next_action.action)
        self.assertIn("项目交流群（3）", card.next_action.why)

        scored_metrics = [card.overall, card.relationship_strength, card.recency, card.reciprocity]
        for metric in scored_metrics:
            self.assertTrue(metric.evidence, metric.name)
            self.assertTrue(metric.explanation, metric.name)
            for evidence in metric.evidence:
                self.assertTrue(evidence.captured_at, metric.name)
                self.assertTrue(evidence.source_chat, metric.name)
                self.assertTrue(evidence.excerpt, metric.name)

    def test_quality_markdown_renders_relationship_operating_desk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_quality_data(db_path)

            cards = build_relationship_quality_cards(
                db_path,
                as_of="2026-05-27T12:00:00+08:00",
                min_suggestion_score=0,
            )
            markdown = render_relationship_quality_markdown(cards)

        self.assertIn("# 关系运营台", markdown)
        self.assertIn("| 人 | 总分 | 关系强度 | 最近互动 | 互惠 | 场景 | 风险 | 资料缺口 | 下一步 |", markdown)
        self.assertIn("| 群成员A |", markdown)
        self.assertIn("项目跟进", markdown)
        self.assertIn("## 群成员A", markdown)
        self.assertIn("### 评分证据", markdown)
        self.assertIn("- 总分：", markdown)
        self.assertIn("证据：项目交流群（3） / 2026-05-27 09:00", markdown)


def _seed_quality_data(db_path: Path) -> None:
    init_db(db_path)
    ingest_capture(
        db_path,
        raw_text=(
            "项目交流群（3）\n"
            "群成员A\n"
            "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。或者咱们打算往哪个方向做，我再研究。"
        ),
        contact_hint="项目交流群（3）",
        source="test",
        captured_at="2026-05-27T09:00:00+08:00",
        image_path="/tmp/group-a.png",
    )
    ingest_capture(
        db_path,
        raw_text="李四\n最近看到一篇文章，挺有意思。",
        contact_hint="李四",
        source="test",
        captured_at="2026-04-01T09:00:00+08:00",
    )


if __name__ == "__main__":
    unittest.main()
