import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from wsa.cli import main


class IngestCommandTests(unittest.TestCase):
    def test_ingest_prints_chinese_signal_labels(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "ingest",
                        "--contact",
                        "王志平",
                        "--text",
                        "智能客服项目本周推出还有哪些工作？我还需要提供哪些？",
                    ]
                )

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("contact=王志平", output)
        self.assertIn("signals=项目/合作,问题", output)
        self.assertNotIn("project", output)
        self.assertNotIn("question", output)

    def test_ingest_prints_chinese_empty_signal_label(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "ingest",
                        "--contact",
                        "李四",
                        "--text",
                        "最近看到一篇文章，挺有意思。",
                    ]
                )

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("contact=李四", output)
        self.assertIn("signals=无", output)
        self.assertNotIn("signals=none", output)


if __name__ == "__main__":
    unittest.main()
