import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from wsa.cli import main


class EmptyReportCommandTests(unittest.TestCase):
    def test_suggest_initializes_missing_database_and_prints_empty_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "suggest"])

            output = stdout.getvalue()
            self.assertEqual(0, exit_code)
            self.assertTrue(db_path.exists())
            self.assertIn("# 社交跟进建议", output)
            self.assertIn("暂无需要跟进的联系人。", output)

    def test_profiles_initializes_missing_database_and_prints_empty_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "profiles"])

            output = stdout.getvalue()
            self.assertEqual(0, exit_code)
            self.assertTrue(db_path.exists())
            self.assertIn("# 联系人关系档案", output)
            self.assertIn("暂无联系人档案。", output)


if __name__ == "__main__":
    unittest.main()
