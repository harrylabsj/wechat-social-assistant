import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from wsa.cli import main
from wsa.store import ingest_capture, init_db


GROUP_CHAT = "AI路演群（12）"


class CandidateCommandTests(unittest.TestCase):
    def test_candidates_command_outputs_and_syncs_group_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_candidate_cli_data(db_path)

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "candidates",
                        "--sync",
                        "--min-confidence",
                        "0",
                    ]
                )

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("# 人脉候选人", output)
        self.assertIn("张三", output)
        self.assertIn(GROUP_CHAT, output)

    def test_candidate_confirm_requires_yes_and_marks_candidate_confirmed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_candidate_cli_data(db_path)
            with contextlib.redirect_stdout(io.StringIO()):
                main(["--db", str(db_path), "candidates", "--sync", "--min-confidence", "0"])

            with self.assertRaises(SystemExit):
                main(
                    [
                        "--db",
                        str(db_path),
                        "candidate-confirm",
                        "张三",
                        "--source-chat",
                        GROUP_CHAT,
                    ]
                )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "candidate-confirm",
                        "张三",
                        "--source-chat",
                        GROUP_CHAT,
                        "--yes",
                        "--confirmed-at",
                        "2026-05-27T10:00:00+08:00",
                    ]
                )

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("confirmed candidate", output)
        self.assertIn("张三", output)
        self.assertIn(GROUP_CHAT, output)


def _seed_candidate_cli_data(db_path: Path) -> None:
    init_db(db_path)
    ingest_capture(
        db_path,
        raw_text=(
            f"{GROUP_CHAT}\n"
            "张三\n"
            "我是星火科技的张三，最近在做AI社交助手，想找医疗场景合作伙伴。\n"
            "李四\n"
            "我在北大国发院做医疗AI研究，可以下周聊聊。"
        ),
        contact_hint=GROUP_CHAT,
        source="test",
        captured_at="2026-05-27T09:00:00+08:00",
    )


if __name__ == "__main__":
    unittest.main()
