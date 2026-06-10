import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from wsa.feedback import list_feedback, record_feedback
from wsa.suggestions import build_suggestions
from wsa.store import ingest_capture, init_db


class FeedbackLoopTests(unittest.TestCase):
    def test_record_and_list_feedback_is_local_and_auditable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)

            result = record_feedback(
                db_path,
                person_name="李四",
                action="too_pushy",
                note="这个草稿太主动，放轻一点。",
                created_at="2026-05-27T10:00:00+08:00",
            )
            rows = list_feedback(db_path, person_name="李四")

        self.assertEqual("李四", result.person_name)
        self.assertEqual("too_pushy", result.action)
        self.assertEqual(1, len(rows))
        self.assertEqual(result.id, rows[0].id)
        self.assertEqual("这个草稿太主动，放轻一点。", rows[0].note)

    def test_invalid_feedback_action_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)

            with self.assertRaises(ValueError):
                record_feedback(db_path, person_name="李四", action="delete_everything")

    def test_do_not_contact_suppresses_suggestions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_project_followup(db_path)
            record_feedback(
                db_path,
                person_name="李四",
                action="do_not_contact",
                created_at="2026-05-27T10:00:00+08:00",
            )

            suggestions = build_suggestions(
                db_path,
                as_of="2026-05-27T12:00:00+08:00",
                min_score=0,
            )

        self.assertNotIn("李四", [suggestion.person_name for suggestion in suggestions])

    def test_snooze_suppresses_until_the_selected_time(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_project_followup(db_path)
            record_feedback(
                db_path,
                person_name="李四",
                action="snooze",
                until_at="2026-05-30T09:00:00+08:00",
                created_at="2026-05-27T10:00:00+08:00",
            )

            before = build_suggestions(db_path, as_of="2026-05-28T12:00:00+08:00", min_score=0)
            after = build_suggestions(db_path, as_of="2026-05-31T12:00:00+08:00", min_score=0)

        self.assertNotIn("李四", [suggestion.person_name for suggestion in before])
        self.assertIn("李四", [suggestion.person_name for suggestion in after])

    def test_snooze_date_is_normalized_to_aware_timestamp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_project_followup(db_path)

            record = record_feedback(
                db_path,
                person_name="李四",
                action="snooze",
                until_at="2026-06-30",
                created_at="2026-05-27T10:00:00+08:00",
            )
            suggestions = build_suggestions(db_path, as_of="2026-05-28T12:00:00+08:00", min_score=0)

        self.assertTrue(record.until_at.startswith("2026-06-30T00:00:00"))
        self.assertIsNotNone(datetime.fromisoformat(record.until_at).tzinfo)
        self.assertNotIn("李四", [suggestion.person_name for suggestion in suggestions])

    def test_invalid_feedback_timestamp_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)

            with self.assertRaisesRegex(ValueError, "invalid ISO timestamp or date"):
                record_feedback(
                    db_path,
                    person_name="李四",
                    action="snooze",
                    until_at="tomorrow",
                    created_at="2026-05-27T10:00:00+08:00",
                )
            rows = list_feedback(db_path, person_name="李四")

        self.assertEqual([], rows)

    def test_mark_done_suppresses_current_evidence_but_new_capture_reopens_followup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_project_followup(db_path, captured_at="2026-05-27T09:00:00+08:00")
            record_feedback(
                db_path,
                person_name="李四",
                action="mark_done",
                created_at="2026-05-27T10:00:00+08:00",
            )
            suppressed = build_suggestions(db_path, as_of="2026-05-27T12:00:00+08:00", min_score=0)
            ingest_capture(
                db_path,
                raw_text="李四\n新项目这周需要再确认一下时间。",
                contact_hint="李四",
                source="test",
                captured_at="2026-05-27T11:00:00+08:00",
            )
            reopened = build_suggestions(db_path, as_of="2026-05-27T12:00:00+08:00", min_score=0)

        self.assertNotIn("李四", [suggestion.person_name for suggestion in suppressed])
        self.assertIn("李四", [suggestion.person_name for suggestion in reopened])

    def test_too_pushy_softens_draft_and_lowers_score(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            plain_db = Path(tmpdir) / "plain" / "social.db"
            tuned_db = Path(tmpdir) / "tuned" / "social.db"
            _seed_project_followup(plain_db)
            _seed_project_followup(tuned_db)
            record_feedback(
                tuned_db,
                person_name="李四",
                action="too_pushy",
                created_at="2026-05-27T10:00:00+08:00",
            )

            plain = build_suggestions(plain_db, as_of="2026-05-27T12:00:00+08:00", min_score=0)[0]
            tuned = build_suggestions(tuned_db, as_of="2026-05-27T12:00:00+08:00", min_score=0)[0]

        self.assertLess(tuned.score, plain.score)
        self.assertIn("不急", tuned.draft)
        self.assertIn("上次草稿反馈：太主动", tuned.why)

    def test_good_draft_boosts_similar_future_suggestions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_project_followup(db_path)
            record_feedback(
                db_path,
                person_name="李四",
                action="good_draft",
                created_at="2026-05-27T10:00:00+08:00",
            )

            suggestions = build_suggestions(db_path, as_of="2026-05-27T12:00:00+08:00", min_score=0)

        self.assertEqual("李四", suggestions[0].person_name)
        self.assertIn("用户反馈过类似草稿可用", suggestions[0].why)
        self.assertGreaterEqual(suggestions[0].score, 55)


def _seed_project_followup(db_path: Path, *, captured_at: str = "2026-05-27T09:00:00+08:00") -> None:
    init_db(db_path)
    ingest_capture(
        db_path,
        raw_text="李四\n下周方便聊聊你那个新项目吗？",
        contact_hint="李四",
        source="test",
        captured_at=captured_at,
    )


if __name__ == "__main__":
    unittest.main()
