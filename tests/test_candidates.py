import tempfile
import unittest
from pathlib import Path

from wsa.candidates import (
    confirm_relationship_candidate,
    discover_relationship_candidates,
    list_relationship_candidates,
    render_candidates_markdown,
    sync_relationship_candidates,
)
from wsa.store import connect, ingest_capture, init_db


GROUP_CHAT = "AI路演群（12）"


class RelationshipCandidateTests(unittest.TestCase):
    def test_discovers_candidate_relationships_from_event_like_group_chats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_candidate_data(db_path)

            candidates = discover_relationship_candidates(db_path, min_confidence=0)

        names = {candidate.name for candidate in candidates}
        self.assertIn("张三", names)
        self.assertIn("李四", names)
        zhang = next(candidate for candidate in candidates if candidate.name == "张三")
        self.assertEqual("pending", zhang.status)
        self.assertEqual(GROUP_CHAT, zhang.source_chat)
        self.assertEqual("2026-05-27T09:00:00+08:00", zhang.evidence_captured_at)
        self.assertGreaterEqual(zhang.confidence, 60)
        self.assertTrue(any("群/活动" in reason for reason in zhang.reasons))
        self.assertIn("星火科技", " ".join(zhang.reasons))
        self.assertIn("AI社交助手", zhang.evidence_excerpt)
        self.assertIn(GROUP_CHAT, zhang.icebreaker_draft)
        self.assertIn("张三", zhang.icebreaker_draft)

    def test_sync_is_idempotent_and_confirmation_promotes_candidate_to_contact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_candidate_data(db_path)

            first = sync_relationship_candidates(db_path, min_confidence=0)
            second = sync_relationship_candidates(db_path, min_confidence=0)
            pending = list_relationship_candidates(db_path, status="pending")
            confirmed = confirm_relationship_candidate(
                db_path,
                name="张三",
                source_chat=GROUP_CHAT,
                confirmed_at="2026-05-27T10:00:00+08:00",
                note="准备线下认识",
            )
            after_confirm = list_relationship_candidates(db_path, status="confirmed")
            with connect(db_path) as conn:
                row_count = conn.execute(
                    """
                    select count(*) from relationship_candidates
                    where name = ? and source_chat = ?
                    """,
                    ("张三", GROUP_CHAT),
                ).fetchone()[0]
                person = conn.execute("select name from people where name = ?", ("张三",)).fetchone()

        self.assertEqual(len(first), len(second))
        self.assertEqual(1, row_count)
        self.assertIn("张三", {candidate.name for candidate in pending})
        self.assertEqual("confirmed", confirmed.status)
        self.assertEqual("准备线下认识", confirmed.note)
        self.assertIn("张三", {candidate.name for candidate in after_confirm})
        self.assertIsNotNone(person)

    def test_render_candidates_markdown_is_contact_centered(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_candidate_data(db_path)
            candidates = discover_relationship_candidates(db_path, min_confidence=0)

            markdown = render_candidates_markdown(candidates)

        self.assertIn("# 人脉候选人", markdown)
        self.assertIn("| 姓名 | 来源 | 置信度 | 状态 | 理由 | 破冰草稿 |", markdown)
        self.assertIn("张三", markdown)
        self.assertIn(GROUP_CHAT, markdown)
        self.assertIn("AI社交助手", markdown)


def _seed_candidate_data(db_path: Path) -> None:
    init_db(db_path)
    ingest_capture(
        db_path,
        raw_text=(
            f"{GROUP_CHAT}\n"
            "张三\n"
            "我是星火科技的张三，最近在做AI社交助手，想找医疗场景合作伙伴。\n"
            "李四\n"
            "我在北大国发院做医疗AI研究，可以下周聊聊。"
        ),
        contact_hint=GROUP_CHAT,
        source="test",
        captured_at="2026-05-27T09:00:00+08:00",
    )


if __name__ == "__main__":
    unittest.main()
