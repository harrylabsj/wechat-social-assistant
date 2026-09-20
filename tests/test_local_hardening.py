"""Local-privacy and resilience guarantees that are easy to regress silently."""

import _env_guard  # noqa: F401 - scrub inherited WSA_* before importing wsa

import contextlib
import io
import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from wsa.audit import export_local_data
from wsa.cli import build_parser, cmd_watch
from wsa.ocr import CaptureError
from wsa.settings import DATA_DIR_MODE, DATA_FILE_MODE, save_watch_interval
from wsa.store import ingest_capture, init_db


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


class DataPermissionTests(unittest.TestCase):
    """WeChat conversations must not be readable by other accounts on the Mac."""

    def test_database_directory_and_settings_are_owner_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            save_watch_interval(db_path, 60)
            settings = db_path.parent / "settings.json"

            self.assertEqual(DATA_FILE_MODE, _mode(db_path))
            self.assertEqual(DATA_DIR_MODE, _mode(db_path.parent))
            self.assertEqual(DATA_FILE_MODE, _mode(settings))

    def test_local_data_export_is_owner_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            ingest_capture(
                db_path,
                raw_text="王五\n下周方便聊聊吗？",
                contact_hint="王五",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
            )
            out = root / "export" / "local-data.json"
            out.parent.mkdir(parents=True)
            user_dir_mode = _mode(out.parent)

            export_local_data(db_path, out_path=out)

            # The export file itself is owner-only, but a directory the user
            # chose is left with its own permissions: re-permissioning it
            # would tighten unrelated parts of their filesystem.
            self.assertEqual(DATA_FILE_MODE, _mode(out))
            self.assertEqual(user_dir_mode, _mode(out.parent))
            self.assertNotEqual(DATA_DIR_MODE, _mode(out.parent))


class DirectoryPermissionTests(unittest.TestCase):
    """User-chosen output directories keep their permissions (H-2)."""

    def test_secure_directory_tightens_but_output_directory_does_not(self):
        from wsa.settings import ensure_output_directory, secure_directory

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            existing = root / "Documents"
            existing.mkdir()
            existing_mode = _mode(existing)

            self.assertEqual(existing_mode, _mode(ensure_output_directory(existing)))

            created = root / "fresh" / "nested"
            ensure_output_directory(created)
            self.assertNotEqual(DATA_DIR_MODE, _mode(created))

            secure_directory(root / "wsa-data")
            self.assertEqual(DATA_DIR_MODE, _mode(root / "wsa-data"))


class WatchResilienceTests(unittest.TestCase):
    def test_watch_survives_an_unexpected_capture_error(self):
        """watch usually runs detached; one bad cycle must not end capture."""

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            log_file = root / "data" / "watch.log"
            args = build_parser().parse_args(
                ["--db", str(db_path), "watch", "--interval", "5", "--log-file", str(log_file)]
            )
            calls = {"count": 0}

            def flaky_capture(_args):
                calls["count"] += 1
                raise OSError("No space left on device")

            def stop_after_two(_seconds):
                if calls["count"] >= 2:
                    raise KeyboardInterrupt
                return None

            with (
                patch(
                    "wsa.cli.frontmost_app_status",
                    return_value=SimpleNamespace(name="微信", method="swift", detail="ok"),
                ),
                patch("wsa.cli._capture_once", side_effect=flaky_capture),
                patch("wsa.cli.time.sleep", side_effect=stop_after_two),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(KeyboardInterrupt),
            ):
                cmd_watch(args)

            log_text = log_file.read_text(encoding="utf-8")

        self.assertGreaterEqual(calls["count"], 2, "watch stopped after the first failure")
        self.assertIn("unexpected OSError", log_text)
        self.assertIn("No space left on device", log_text)


class ToolchainPreflightTests(unittest.TestCase):
    def test_missing_swiftc_reports_an_actionable_message(self):
        from wsa import ocr

        with tempfile.TemporaryDirectory() as tmpdir:
            binary = Path(tmpdir) / "macos_ocr"
            with (
                patch.object(ocr, "OCR_BINARY", binary),
                patch.object(ocr, "shutil") as fake_shutil,
            ):
                fake_shutil.which.return_value = None
                with self.assertRaises(CaptureError) as ctx:
                    ocr.ensure_ocr_helper()

        self.assertIn("xcode-select --install", str(ctx.exception))


class BackupPassphraseTests(unittest.TestCase):
    def test_passphrase_env_must_be_a_wsa_variable(self):
        from wsa.privacy import encrypted_backup_database

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            init_db(db_path)

            with patch.dict(os.environ, {"LANG": "en_US.UTF-8"}):
                with self.assertRaises(ValueError) as ctx:
                    encrypted_backup_database(
                        db_path, root / "backup.enc", passphrase_env="LANG"
                    )

        self.assertIn("WSA_", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
