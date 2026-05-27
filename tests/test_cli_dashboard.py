import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from wsa.cli import main
from wsa.store import ingest_capture, init_db


class DashboardCommandTests(unittest.TestCase):
    def test_dashboard_command_renders_operating_view(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="张三\n你上次提到的问题，我这边还没回复，今天补给你。",
                contact_hint="张三",
                source="test",
                captured_at="2026-05-27T09:00:00+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "dashboard",
                        "--as-of",
                        "2026-05-27T12:00:00+08:00",
                        "--min-score",
                        "0",
                    ]
                )

        self.assertEqual(0, exit_code)
        output = stdout.getvalue()
        self.assertIn("# 关系驾驶舱", output)
        self.assertIn("## 优先联系", output)
        self.assertIn("张三", output)


if __name__ == "__main__":
    unittest.main()
