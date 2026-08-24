import subprocess
import tempfile
import unittest
from pathlib import Path

from wsa.audit import export_local_data
from wsa.privacy import encrypted_backup_database, purge_expired_captures, redact_text
from wsa.store import connect, ingest_capture, init_db


class PrivacyTests(unittest.TestCase):
    def test_redact_text_and_default_export_remove_common_identifiers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="张三\n电话 13812345678，邮箱 a@example.com，资料 https://example.com/a",
                contact_hint="张三",
                source="test",
            )
            export_path = root / "export.json"
            export_local_data(db_path, out_path=export_path)
            payload = export_path.read_text(encoding="utf-8")

        self.assertEqual("电话 [PHONE]，邮箱 [EMAIL]，资料 [URL]", redact_text("电话 13812345678，邮箱 a@example.com，资料 https://example.com/a"))
        self.assertNotIn("13812345678", payload)
        self.assertNotIn("a@example.com", payload)
        self.assertTrue("[PHONE]" in payload)

    def test_purge_retention_is_previewable_and_cascades_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            captures = db_path.parent / "captures"
            captures.mkdir(parents=True)
            image = captures / "old.png"
            image.write_bytes(b"old")
            ingest_capture(
                db_path,
                raw_text="张三\n一条旧消息",
                contact_hint="张三",
                source="test",
                captured_at="2025-01-01T00:00:00+08:00",
                image_path=str(image),
                image_managed=True,
            )
            dry = purge_expired_captures(db_path, retention_days=30, as_of="2025-02-15T00:00:00+08:00", dry_run=True)
            self.assertEqual(1, dry.matched_captures)
            self.assertTrue(image.exists())
            result = purge_expired_captures(db_path, retention_days=30, as_of="2025-02-15T00:00:00+08:00", dry_run=False)
            with connect(db_path) as conn:
                counts = [
                    conn.execute(f"select count(*) from {table}").fetchone()[0]
                    for table in ("captures", "perception_runs", "message_candidates", "relation_events")
                ]

        self.assertEqual(1, result.removed_captures)
        self.assertEqual(1, result.removed_screenshots)
        self.assertFalse(image.exists())
        self.assertEqual([0, 0, 0, 0], counts)

    def test_encrypted_backup_never_leaves_plaintext_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "social.db"
            encrypted = root / "social.db.enc"
            init_db(db_path)
            ingest_capture(db_path, raw_text="张三\n本地备份", contact_hint="张三")
            encrypted_backup_database(db_path, encrypted, passphrase="test-passphrase")
            decrypted = root / "decrypted.db"
            subprocess.run(
                ["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-pass", "stdin", "-in", str(encrypted), "-out", str(decrypted)],
                input="test-passphrase\n",
                text=True,
                capture_output=True,
                check=True,
            )
            encrypted_exists = encrypted.exists()
            decrypted_exists = decrypted.exists()
            decrypted_size = decrypted.stat().st_size

        self.assertTrue(encrypted_exists)
        self.assertTrue(decrypted_exists)
        self.assertGreater(decrypted_size, 0)


if __name__ == "__main__":
    unittest.main()
