"""Every delete path must act on rows this database owns, never on a directory.

The regressions guarded here caused real, unrecoverable data loss: a reset
against a throwaway database resolved its screenshot directory from the
ambient ``WSA_CAPTURES_DIR`` and deleted an unrelated screenshot library.
"""

import _env_guard  # noqa: F401 - scrub inherited WSA_* before importing wsa

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wsa.audit import delete_contact_data
from wsa.privacy import purge_expired_captures
from wsa.store import connect, ingest_capture, init_db, reset_memory

from _env_guard import WSA_ENVIRONMENT_PREFIX, scrub_wsa_environment


class EnvironmentGuardTests(unittest.TestCase):
    def test_wsa_environment_is_scrubbed_before_tests_run(self):
        leaked = sorted(name for name in os.environ if name.startswith(WSA_ENVIRONMENT_PREFIX))

        self.assertEqual(
            [],
            leaked,
            "tests/_env_guard.py did not run before wsa was imported; a test could "
            "now resolve real data paths from the shell environment",
        )

    def test_scrub_removes_variables_added_later(self):
        with patch.dict(os.environ, {"WSA_CAPTURES_DIR": "/tmp/should-not-survive"}):
            removed = scrub_wsa_environment()

            self.assertIn("WSA_CAPTURES_DIR", removed)
            self.assertNotIn("WSA_CAPTURES_DIR", os.environ)


class ResetScopeTests(unittest.TestCase):
    def test_reset_never_deletes_files_this_database_does_not_own(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            captures_dir = root / "data" / "captures"
            captures_dir.mkdir(parents=True)

            owned = captures_dir / "owned.png"
            imported = captures_dir / "imported.png"
            orphan = captures_dir / "orphan.png"
            for image in (owned, imported, orphan):
                image.write_bytes(b"png")

            ingest_capture(
                db_path,
                raw_text="王五\n下周方便聊聊吗？",
                contact_hint="王五",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
                image_path=str(owned),
                image_managed=True,
            )
            ingest_capture(
                db_path,
                raw_text="赵六\n资料收到了，谢谢",
                contact_hint="赵六",
                source="import-image",
                captured_at="2026-05-26T10:00:00+08:00",
                image_path=str(imported),
                image_managed=False,
            )

            result = reset_memory(db_path, captures_dir=captures_dir)

            self.assertEqual(1, result.removed_screenshots)
            self.assertEqual((owned.resolve(),), result.screenshot_paths)
            self.assertFalse(owned.exists(), "the managed screenshot should be deleted")
            self.assertTrue(imported.exists(), "a user-imported image must survive reset")
            self.assertTrue(orphan.exists(), "an unreferenced file must survive reset")

    def test_reset_does_not_touch_another_databases_screenshots(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            shared_dir = root / "shared-captures"
            shared_dir.mkdir(parents=True)
            other_image = shared_dir / "other-library.png"
            other_image.write_bytes(b"png")

            other_db = root / "other" / "data" / "social.db"
            ingest_capture(
                other_db,
                raw_text="孙七\n明天见",
                contact_hint="孙七",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
                image_path=str(other_image),
                image_managed=True,
            )

            throwaway_db = root / "throwaway" / "data" / "social.db"
            init_db(throwaway_db)

            result = reset_memory(throwaway_db, captures_dir=shared_dir)

            self.assertEqual(0, result.removed_screenshots)
            self.assertTrue(
                other_image.exists(),
                "resetting an empty database must not delete another database's screenshots",
            )
            with connect(other_db) as conn:
                self.assertEqual(1, conn.execute("select count(*) from captures").fetchone()[0])

    def test_reset_dry_run_reports_paths_without_deleting(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            captures_dir = root / "data" / "captures"
            captures_dir.mkdir(parents=True)
            image = captures_dir / "owned.png"
            image.write_bytes(b"png")
            ingest_capture(
                db_path,
                raw_text="王五\n下周方便聊聊吗？",
                contact_hint="王五",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
                image_path=str(image),
                image_managed=True,
            )

            result = reset_memory(db_path, captures_dir=captures_dir, dry_run=True)

            self.assertEqual((image.resolve(),), result.screenshot_paths)
            self.assertTrue(image.exists())


class DeleteContactScopeTests(unittest.TestCase):
    def test_delete_contact_keeps_images_shared_with_another_contact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            captures_dir = root / "data" / "captures"
            captures_dir.mkdir(parents=True)
            shared = captures_dir / "shared.png"
            shared.write_bytes(b"png")

            for contact, text in (("王五", "下周方便聊聊吗？"), ("赵六", "资料收到了")):
                ingest_capture(
                    db_path,
                    raw_text=f"{contact}\n{text}",
                    contact_hint=contact,
                    source="test",
                    captured_at="2026-05-26T09:00:00+08:00",
                    image_path=str(shared),
                    image_managed=True,
                )

            result = delete_contact_data(db_path, "王五")

            self.assertEqual(0, result.removed_screenshots)
            self.assertTrue(shared.exists(), "an image another contact still references must survive")


class PurgeScopeTests(unittest.TestCase):
    def test_purge_keeps_unmanaged_and_unreferenced_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            captures_dir = root / "data" / "captures"
            captures_dir.mkdir(parents=True)
            managed = captures_dir / "managed.png"
            imported = captures_dir / "imported.png"
            orphan = captures_dir / "orphan.png"
            for image in (managed, imported, orphan):
                image.write_bytes(b"png")

            ingest_capture(
                db_path,
                raw_text="王五\n下周方便聊聊吗？",
                contact_hint="王五",
                source="test",
                captured_at="2020-01-01T09:00:00+08:00",
                image_path=str(managed),
                image_managed=True,
            )
            ingest_capture(
                db_path,
                raw_text="赵六\n资料收到了",
                contact_hint="赵六",
                source="import-image",
                captured_at="2020-01-01T10:00:00+08:00",
                image_path=str(imported),
                image_managed=False,
            )

            with patch("wsa.privacy.capture_storage_roots", return_value=(captures_dir.resolve(),)):
                result = purge_expired_captures(db_path, retention_days=30, dry_run=False)

            self.assertEqual(2, result.removed_captures)
            self.assertEqual(1, result.removed_screenshots)
            self.assertFalse(managed.exists())
            self.assertTrue(imported.exists())
            self.assertTrue(orphan.exists())


if __name__ == "__main__":
    unittest.main()
