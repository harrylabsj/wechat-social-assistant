import sqlite3
import tempfile
import unittest
from pathlib import Path

from wsa.observations import OCRObservation
from wsa.audit import delete_contact_data
from wsa.reviews import (
    REVIEW_CONFIRMATION_TEXT,
    OCRReviewError,
    list_ocr_reviews,
    record_ocr_review,
)
from wsa.store import DatabaseMigrationError, backup_database, ingest_capture, init_db, schema_version


class OCRReviewTests(unittest.TestCase):
    def test_pending_review_and_correction_update_effective_capture_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            result = ingest_capture(
                db_path,
                raw_text="张三\n下周聊聊项目",
                contact_hint="张三",
                source="test",
                interaction_at=None,
                observations=(
                    OCRObservation(text="张三", confidence=0.98, source="vision"),
                    OCRObservation(text="下周聊聊项目", confidence=0.42, source="vision"),
                ),
            )

            pending = list_ocr_reviews(db_path, max_confidence=0.75)
            self.assertEqual(["下周聊聊项目"], [item.text for item in pending])
            self.assertEqual("pending", pending[0].status)

            review = record_ocr_review(
                db_path,
                observation_id=pending[0].observation_id,
                action="correct",
                corrected_text="下周聊聊项目和预算",
                note="人工确认截图中的完整句子",
                confirmed=True,
                confirmation_text=REVIEW_CONFIRMATION_TEXT,
                reviewed_at="2026-05-27T10:00:00+08:00",
            )

            self.assertEqual("corrected", review.review.status)
            self.assertEqual("下周聊聊项目和预算", review.review.effective_text)
            self.assertTrue(review.capture_text_changed)
            with sqlite3.connect(db_path) as conn:
                row = conn.execute("select clean_text, corrected_text from captures where id = ?", (result.capture_id,)).fetchone()
                events = conn.execute("select action from ocr_review_events").fetchall()
            self.assertEqual("下周聊聊项目", row[0])
            self.assertEqual("下周聊聊项目和预算", row[1])
            self.assertEqual([("correct",)], events)

            completed = list_ocr_reviews(db_path, status="corrected", max_confidence=None)
            self.assertEqual(1, len(completed))
            self.assertEqual("下周聊聊项目和预算", completed[0].effective_text)

    def test_reject_removes_line_but_raw_evidence_stays(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            result = ingest_capture(
                db_path,
                raw_text="张三\n乱码",
                contact_hint="张三",
                interaction_at=None,
                observations=(
                    OCRObservation(text="张三", confidence=0.99),
                    OCRObservation(text="乱码", confidence=0.1),
                ),
            )
            pending = list_ocr_reviews(db_path, max_confidence=0.2)
            record_ocr_review(
                db_path,
                observation_id=pending[0].observation_id,
                action="reject",
                confirmed=True,
                confirmation_text=REVIEW_CONFIRMATION_TEXT,
            )
            with sqlite3.connect(db_path) as conn:
                row = conn.execute("select raw_text, clean_text, corrected_text from captures where id = ?", (result.capture_id,)).fetchone()
            self.assertEqual("张三\n乱码", row[0])
            self.assertEqual("乱码", row[1])
            self.assertEqual("", row[2])

    def test_review_requires_exact_confirmation_and_valid_correction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(db_path, raw_text="张三\n低置信度", contact_hint="张三", interaction_at=None)
            observation_id = list_ocr_reviews(db_path, max_confidence=None)[0].observation_id

            with self.assertRaises(OCRReviewError):
                record_ocr_review(
                    db_path,
                    observation_id=observation_id,
                    action="correct",
                    confirmed=True,
                    confirmation_text="wrong",
                )
            with self.assertRaises(OCRReviewError):
                record_ocr_review(
                    db_path,
                    observation_id=observation_id,
                    action="correct",
                    confirmed=True,
                    confirmation_text=REVIEW_CONFIRMATION_TEXT,
                )

    def test_schema_version_and_consistent_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "social.db"
            backup = root / "backups" / "social.db"
            init_db(db_path)
            self.assertEqual(5, schema_version(db_path))
            ingest_capture(db_path, raw_text="张三\n你好", contact_hint="张三", interaction_at=None)
            backup_database(db_path, backup)
            with sqlite3.connect(backup) as conn:
                self.assertEqual(1, conn.execute("select count(*) from captures").fetchone()[0])
                self.assertEqual(5, conn.execute("select max(version) from schema_migrations").fetchone()[0])

    def test_newer_database_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            with sqlite3.connect(db_path) as conn:
                conn.execute("insert or replace into schema_migrations(version, applied_at) values (99, 'future')")
            with self.assertRaises(DatabaseMigrationError):
                init_db(db_path)

    def test_delete_contact_reports_and_removes_review_audit_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest = ingest_capture(
                db_path,
                raw_text="张三\n低质量内容",
                contact_hint="张三",
                interaction_at=None,
                observations=(OCRObservation(text="张三"), OCRObservation(text="低质量内容", confidence=0.1)),
            )
            low = list_ocr_reviews(db_path, max_confidence=0.2)[0]
            record_ocr_review(
                db_path,
                observation_id=low.observation_id,
                action="reject",
                confirmed=True,
                confirmation_text=REVIEW_CONFIRMATION_TEXT,
            )
            result = delete_contact_data(db_path, "张三")
            self.assertEqual(1, result.removed_reviews)
            self.assertEqual(1, result.removed_review_events)
            with sqlite3.connect(db_path) as conn:
                self.assertEqual(0, conn.execute("select count(*) from ocr_reviews").fetchone()[0])
                self.assertEqual(0, conn.execute("select count(*) from ocr_review_events").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
