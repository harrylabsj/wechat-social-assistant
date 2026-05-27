import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from wsa.cli import main
from wsa.store import ingest_capture, init_db


class QualityCommandTests(unittest.TestCase):
    def test_quality_command_outputs_relationship_operating_desk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_quality_cli_data(db_path)

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "quality",
                        "--contact",
                        "群成员A",
                        "--min-score",
                        "0",
                        "--as-of",
                        "2026-05-27T12:00:00+08:00",
                    ]
                )

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("# 关系运营台", output)
        self.assertIn("| 群成员A |", output)
        self.assertIn("项目跟进", output)
        self.assertIn("仅群聊上下文，主动联系前需要保持克制", output)
        self.assertIn("缺少私聊互动证据", output)
        self.assertIn("### 评分证据", output)
        self.assertIn("证据：项目交流群（3） / 2026-05-27 09:00", output)

    def test_quality_command_writes_markdown_when_out_is_provided(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            out_path = root / "reports" / "quality.md"
            _seed_quality_cli_data(db_path)

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "quality", "--out", str(out_path)])
            written = out_path.read_text(encoding="utf-8")

        self.assertEqual(0, exit_code)
        self.assertIn(f"wrote {out_path}", stdout.getvalue())
        self.assertIn("# 关系运营台", written)


def _seed_quality_cli_data(db_path: Path) -> None:
    init_db(db_path)
    ingest_capture(
        db_path,
        raw_text=(
            "项目交流群（3）\n"
            "群成员A\n"
            "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。或者咱们打算往哪个方向做，我再研究。"
        ),
        contact_hint="项目交流群（3）",
        source="test",
        captured_at="2026-05-27T09:00:00+08:00",
        image_path="/tmp/group-a.png",
    )


if __name__ == "__main__":
    unittest.main()
