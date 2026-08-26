import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wsa.observations import OCRObservation
from wsa.store import EmptyCaptureError, connect, default_db_path, ingest_capture, init_db, list_ocr_observations, reset_memory


class StoreTests(unittest.TestCase):
    def test_default_db_path_honors_user_environment_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            configured = Path(tmpdir) / "wsa" / "data" / "social.db"
            with patch.dict("os.environ", {"WSA_DB": str(configured)}):
                self.assertEqual(configured.resolve(), default_db_path(Path("/ignored")))

    def test_connect_context_manager_closes_connection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)

            with connect(db_path) as conn:
                conn.execute("select 1").fetchone()

            with self.assertRaises(sqlite3.ProgrammingError):
                conn.execute("select 1")

    def test_ingest_capture_upserts_person_and_deduplicates_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)

            first = ingest_capture(
                db_path,
                raw_text="王五\n我最近换工作了，下周方便聊聊吗？",
                contact_hint="王五",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
            )
            second = ingest_capture(
                db_path,
                raw_text="王五\n我最近换工作了，下周方便聊聊吗？",
                contact_hint="王五",
                source="test",
                captured_at="2026-05-26T09:01:00+08:00",
            )

            self.assertTrue(first.inserted)
            self.assertFalse(second.inserted)
            self.assertEqual(first.capture_id, second.capture_id)

            with sqlite3.connect(db_path) as conn:
                people = conn.execute("select name, last_interaction_at from people").fetchall()
                captures = conn.execute("select source from captures").fetchall()
                signals = conn.execute("select kind from capture_signals order by kind").fetchall()

            self.assertEqual([("王五", "2026-05-26T09:00:00+08:00")], people)
            self.assertEqual([("test",)], captures)
            self.assertEqual([("schedule",)], signals)

    def test_duplicate_capture_with_attached_image_updates_recent_interaction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "social.db"
            image = root / "captures" / "duplicate.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"png")
            init_db(db_path)

            ingest_capture(
                db_path,
                raw_text="李四\n最近看到一篇文章，挺有意思。",
                contact_hint="李四",
                source="manual",
                captured_at="2026-05-26T09:00:00+08:00",
            )
            result = ingest_capture(
                db_path,
                raw_text="李四\n最近看到一篇文章，挺有意思。",
                contact_hint="李四",
                source="watch",
                captured_at="2026-05-27T10:00:00+08:00",
                image_path=str(image),
            )

            with connect(db_path) as conn:
                person = conn.execute(
                    "select last_interaction_at from people where name = '李四'"
                ).fetchone()
                capture = conn.execute(
                    "select captured_at, source, image_path from captures"
                ).fetchone()

        self.assertFalse(result.inserted)
        self.assertTrue(result.image_attached)
        self.assertEqual("2026-05-27T10:00:00+08:00", person["last_interaction_at"])
        self.assertEqual("2026-05-27T10:00:00+08:00", capture["captured_at"])
        self.assertEqual("watch", capture["source"])
        self.assertEqual(str(image), capture["image_path"])

    def test_ingest_capture_persists_structured_ocr_observations_and_speaker_candidate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            result = ingest_capture(
                db_path,
                raw_text="项目交流群（3）\n群成员A\n可以参考一下这家",
                contact_hint="项目交流群（3）",
                source="ocr",
                captured_at="2026-05-27T09:00:00+08:00",
                interaction_at=None,
                observations=(
                    OCRObservation(
                        text="项目交流群（3）",
                        confidence=0.99,
                        bbox_x=0.1,
                        bbox_y=0.8,
                        bbox_width=0.2,
                        bbox_height=0.05,
                        source="vision",
                    ),
                    OCRObservation(
                        text="群成员A",
                        confidence=0.9,
                        bbox_x=0.2,
                        bbox_y=0.6,
                        bbox_width=0.1,
                        bbox_height=0.04,
                        source="vision",
                        role="AXStaticText",
                        node_path="0.1.0",
                        parent_path="0.1",
                        depth=3,
                    ),
                    OCRObservation(
                        text="可以参考一下这家",
                        confidence=0.85,
                        bbox_x=0.2,
                        bbox_y=0.55,
                        bbox_width=0.3,
                        bbox_height=0.04,
                        source="vision",
                    ),
                ),
            )

            observations = list_ocr_observations(db_path, capture_id=result.capture_id)

        self.assertEqual(3, len(observations))
        self.assertEqual("vision", observations[1].source)
        self.assertEqual(0.6, observations[1].bbox_y)
        self.assertEqual("群成员A", observations[1].speaker_candidate)
        self.assertEqual(0.55, observations[1].speaker_confidence)
        self.assertEqual("AXStaticText", observations[1].role)
        self.assertEqual("0.1.0", observations[1].node_path)

    def test_ingest_capture_separates_evidence_from_derived_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            result = ingest_capture(
                db_path,
                raw_text="张三\n明天一起吃饭吗？\n项目合作下周推进",
                contact_hint="张三",
                source="accessibility",
                perception_connector="macos-accessibility",
                capture_backend="accessibility",
                observations=(
                    OCRObservation(text="张三", source="accessibility", sequence=0),
                    OCRObservation(text="明天一起吃饭吗？", source="accessibility", sequence=1),
                ),
            )

            with connect(db_path) as conn:
                run = conn.execute(
                    "select connector, backend, status from perception_runs where capture_id = ?",
                    (result.capture_id,),
                ).fetchone()
                messages = conn.execute(
                    "select count(*) from message_candidates where capture_id = ?",
                    (result.capture_id,),
                ).fetchone()[0]
                events = conn.execute(
                    "select event_type, status from relation_events where capture_id = ?",
                    (result.capture_id,),
                ).fetchall()

        self.assertEqual(("macos-accessibility", "accessibility", "completed"), tuple(run))
        self.assertEqual(2, messages)
        self.assertEqual(
            [("project", "candidate"), ("schedule", "candidate")],
            [tuple(row) for row in events],
        )

    def test_ingest_capture_persists_multi_frame_quality_and_ax_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            result = ingest_capture(
                db_path,
                raw_text="张三\n稳定消息",
                contact_hint="张三",
                source="accessibility",
                capture_frames=2,
                capture_stability=0.75,
                observations=(
                    OCRObservation(
                        text="稳定消息",
                        confidence=1.0,
                        source="accessibility",
                        role="AXStaticText",
                        subrole="AXTextLine",
                        node_path="0.2.1",
                        parent_path="0.2",
                        depth=4,
                    ),
                ),
            )
            with connect(db_path) as conn:
                capture = conn.execute(
                    "select capture_frames, capture_stability from captures where id = ?",
                    (result.capture_id,),
                ).fetchone()
            stored = list_ocr_observations(db_path, capture_id=result.capture_id)[0]

        self.assertEqual((2, 0.75), tuple(capture))
        self.assertEqual("AXStaticText", stored.role)
        self.assertEqual("0.2", stored.parent_path)
        self.assertEqual(4, stored.depth)

    def test_init_db_backfills_text_observations_for_existing_capture(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    create table people (
                        id integer primary key autoincrement,
                        name text not null unique,
                        aliases_json text not null default '[]',
                        notes text not null default '',
                        created_at text not null,
                        updated_at text not null,
                        last_interaction_at text
                    );
                    create table captures (
                        id integer primary key autoincrement,
                        person_id integer not null references people(id) on delete cascade,
                        captured_at text not null,
                        source text not null,
                        raw_text text not null,
                        clean_text text not null,
                        text_hash text not null,
                        created_at text not null,
                        unique(person_id, text_hash)
                    );
                    insert into people(name, created_at, updated_at)
                    values ('张三', '2026-05-27T08:00:00+08:00', '2026-05-27T08:00:00+08:00');
                    insert into captures(person_id, captured_at, source, raw_text, clean_text, text_hash, created_at)
                    values (1, '2026-05-27T08:00:00+08:00', 'legacy', '张三\n旧聊天', '旧聊天', 'legacy', '2026-05-27T08:00:00+08:00');
                    """
                )

            init_db(db_path)
            observations = list_ocr_observations(db_path, capture_id=1)

        self.assertEqual(["旧聊天"], [observation.text for observation in observations])
        self.assertEqual(["legacy"], [observation.source for observation in observations])

    def test_duplicate_capture_backfills_missing_signals(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="王五\n我最近换工作了，下周方便聊聊吗？",
                contact_hint="王五",
                source="manual",
                captured_at="2026-05-26T09:00:00+08:00",
            )
            with connect(db_path) as conn:
                conn.execute("delete from capture_signals")
                conn.commit()

            result = ingest_capture(
                db_path,
                raw_text="王五\n我最近换工作了，下周方便聊聊吗？",
                contact_hint="王五",
                source="watch",
                captured_at="2026-05-26T09:01:00+08:00",
            )

            with connect(db_path) as conn:
                signals = conn.execute("select kind from capture_signals order by kind").fetchall()

        self.assertFalse(result.inserted)
        self.assertEqual(("schedule",), result.signal_kinds)
        self.assertEqual(["schedule"], [row["kind"] for row in signals])

    def test_init_db_migrates_existing_captures_without_image_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    create table people (
                        id integer primary key autoincrement,
                        name text not null unique,
                        aliases_json text not null default '[]',
                        notes text not null default '',
                        created_at text not null,
                        updated_at text not null,
                        last_interaction_at text
                    );
                    create table captures (
                        id integer primary key autoincrement,
                        person_id integer not null references people(id) on delete cascade,
                        captured_at text not null,
                        source text not null,
                        raw_text text not null,
                        clean_text text not null,
                        text_hash text not null,
                        created_at text not null,
                        unique(person_id, text_hash)
                    );
                    """
                )

            init_db(db_path)
            result = ingest_capture(
                db_path,
                raw_text="王五\n下周方便聊聊吗？",
                contact_hint="王五",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
                image_path="/tmp/wechat.png",
            )

            with connect(db_path) as conn:
                columns = [row["name"] for row in conn.execute("pragma table_info(captures)").fetchall()]
                capture = conn.execute("select image_path from captures").fetchone()

        self.assertTrue(result.inserted)
        self.assertIn("image_path", columns)
        self.assertEqual("/tmp/wechat.png", capture["image_path"])

    def test_ingest_capture_rejects_empty_clean_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)

            with self.assertRaisesRegex(EmptyCaptureError, "empty"):
                ingest_capture(
                    db_path,
                    raw_text=" \n\t\n",
                    source="ocr",
                    captured_at="2026-05-26T09:00:00+08:00",
                )

            with connect(db_path) as conn:
                people_count = conn.execute("select count(*) from people").fetchone()[0]
                capture_count = conn.execute("select count(*) from captures").fetchone()[0]

        self.assertEqual(0, people_count)
        self.assertEqual(0, capture_count)

    def test_ingest_capture_upserts_group_speakers_as_people(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)

            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "群成员A\n"
                    "可以参考一下这家\n"
                    "群成员A\n"
                    "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-26T22:21:20+08:00",
            )

            with connect(db_path) as conn:
                people = conn.execute(
                    "select name, last_interaction_at from people order by name"
                ).fetchall()
                captures = conn.execute(
                    """
                    select p.name
                    from captures c
                    join people p on p.id = c.person_id
                    """
                ).fetchall()

        self.assertEqual(
            [
                ("群成员A", "2026-05-26T22:21:20+08:00"),
                ("项目交流群（3）", "2026-05-26T22:21:20+08:00"),
            ],
            [(row["name"], row["last_interaction_at"]) for row in people],
        )
        self.assertEqual(["项目交流群（3）"], [row["name"] for row in captures])

    def test_reset_memory_clears_tables_and_image_files_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            captures_dir = root / "data" / "captures"
            captures_dir.mkdir(parents=True)
            image = captures_dir / "wechat.png"
            keep = captures_dir / "notes.txt"
            image.write_bytes(b"png")
            keep.write_text("keep me", encoding="utf-8")
            ingest_capture(
                db_path,
                raw_text="王五\n下周方便聊聊吗？",
                contact_hint="王五",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
                image_path=str(image),
            )

            result = reset_memory(db_path, captures_dir=captures_dir)

            with connect(db_path) as conn:
                people_count = conn.execute("select count(*) from people").fetchone()[0]
                capture_count = conn.execute("select count(*) from captures").fetchone()[0]
                signal_count = conn.execute("select count(*) from capture_signals").fetchone()[0]
            image_exists = image.exists()
            keep_exists = keep.exists()

        self.assertEqual(1, result.removed_screenshots)
        self.assertEqual(1, result.removed_people)
        self.assertEqual(1, result.removed_captures)
        self.assertEqual(1, result.removed_signals)
        self.assertEqual(0, people_count)
        self.assertEqual(0, capture_count)
        self.assertEqual(0, signal_count)
        self.assertFalse(image_exists)
        self.assertTrue(keep_exists)

    def test_reset_memory_dry_run_does_not_delete_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            captures_dir = root / "data" / "captures"
            captures_dir.mkdir(parents=True)
            image = captures_dir / "wechat.png"
            image.write_bytes(b"png")
            ingest_capture(
                db_path,
                raw_text="王五\n下周方便聊聊吗？",
                contact_hint="王五",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
                image_path=str(image),
            )

            result = reset_memory(db_path, captures_dir=captures_dir, dry_run=True)

            with connect(db_path) as conn:
                people_count = conn.execute("select count(*) from people").fetchone()[0]
                capture_count = conn.execute("select count(*) from captures").fetchone()[0]
            image_exists = image.exists()

        self.assertEqual(1, result.removed_screenshots)
        self.assertEqual(1, result.removed_people)
        self.assertEqual(1, result.removed_captures)
        self.assertEqual(1, people_count)
        self.assertEqual(1, capture_count)
        self.assertTrue(image_exists)


if __name__ == "__main__":
    unittest.main()
