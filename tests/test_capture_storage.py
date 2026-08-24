import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from wsa.cli import main
from wsa.settings import (
    ICLOUD_CAPTURE_RELATIVE,
    capture_storage_roots,
    default_captures_dir,
    load_settings,
    resolve_captures_dir,
    save_captures_dir,
    save_watch_interval,
)


class CaptureStorageTests(unittest.TestCase):
    def test_checkout_defaults_to_icloud_when_mounted_on_macos(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            db_path.parent.mkdir()
            (root / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
            icloud = root / "iCloud" / "com~apple~CloudDocs"
            icloud.mkdir(parents=True)

            with patch("wsa.settings.platform.system", return_value="Darwin"), patch(
                "wsa.settings.ICLOUD_DOCUMENTS_ROOT", icloud
            ):
                resolved = default_captures_dir(db_path)

            self.assertEqual((icloud / ICLOUD_CAPTURE_RELATIVE).resolve(), resolved)
            self.assertFalse(resolved.exists())

    def test_non_checkout_or_unmounted_icloud_keeps_local_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            with patch("wsa.settings.platform.system", return_value="Darwin"), patch(
                "wsa.settings.ICLOUD_DOCUMENTS_ROOT", Path(tmpdir) / "missing"
            ):
                self.assertEqual((db_path.parent / "captures").resolve(), default_captures_dir(db_path))

    def test_precedence_is_explicit_then_environment_then_settings_then_auto(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            configured = root / "configured"
            environment = root / "environment"
            explicit = root / "explicit"
            save_captures_dir(db_path, configured)

            self.assertEqual(configured.resolve(), resolve_captures_dir(db_path))
            with patch.dict(os.environ, {"WSA_CAPTURES_DIR": str(environment)}):
                self.assertEqual(environment.resolve(), resolve_captures_dir(db_path))
                self.assertEqual(explicit.resolve(), resolve_captures_dir(db_path, explicit))

    def test_watch_interval_save_preserves_capture_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            configured = Path(tmpdir) / "screenshots"
            save_captures_dir(db_path, configured)
            save_watch_interval(db_path, 12)

            self.assertEqual(configured.resolve(), Path(load_settings(db_path).captures_dir))
            payload = json.loads((db_path.parent / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(12, payload["watch_interval_seconds"])
            self.assertEqual(str(configured.resolve()), payload["captures_dir"])

    def test_cli_reports_and_creates_resolved_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(["--db", str(db_path), "captures-dir", "--create"])

            resolved = resolve_captures_dir(db_path)
            self.assertEqual(0, exit_code)
            self.assertTrue(resolved.is_dir())
            self.assertIn(f"captures_dir={resolved}", output.getvalue())
            self.assertIn("source=auto", output.getvalue())

    def test_storage_roots_include_legacy_local_directory_after_icloud_switch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            (root / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
            icloud = root / "iCloud" / "com~apple~CloudDocs"
            icloud.mkdir(parents=True)

            with patch("wsa.settings.platform.system", return_value="Darwin"), patch(
                "wsa.settings.ICLOUD_DOCUMENTS_ROOT", icloud
            ):
                roots = capture_storage_roots(db_path)

            self.assertEqual(2, len(roots))
            self.assertEqual((icloud / ICLOUD_CAPTURE_RELATIVE).resolve(), roots[0])
            self.assertEqual((db_path.parent / "captures").resolve(), roots[1])


if __name__ == "__main__":
    unittest.main()
