import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from wsa.cli import main
from wsa.store import ingest_capture, init_db


class ObsidianExportCommandTests(unittest.TestCase):
    def test_obsidian_export_writes_contact_files_and_daily_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            vault = root / "Obsidian Vault"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "群成员A\n"
                    "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-26T22:21:20+08:00",
                image_path="/tmp/sunny.png",
            )
            ingest_capture(
                db_path,
                raw_text="陈明 DANIEL\n我是陆陈明 DANIEL 示例资本。幸会！\n陈明\nDaniel Chen",
                contact_hint="陈明 DANIEL",
                source="test",
                captured_at="2026-05-26T22:22:20+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "export-obsidian",
                        "--vault",
                        str(vault),
                        "--date",
                        "2026-05-27",
                    ]
                )

            output = stdout.getvalue()
            people_dir = vault / "社交圈" / "人脉"
            report_dir = vault / "社交圈" / "分析报告"
            people_index_path = people_dir / "索引.md"
            self.assertTrue(people_index_path.exists())
            people_index_text = people_index_path.read_text(encoding="utf-8")
            sunny_text = (people_dir / "群成员A.md").read_text(encoding="utf-8")
            group_text = (people_dir / "项目交流群（3）.md").read_text(encoding="utf-8")
            daniel_text = (people_dir / "陈明 DANIEL.md").read_text(encoding="utf-8")
            report_text = (report_dir / "2026-05-27.md").read_text(encoding="utf-8")

        self.assertEqual(0, exit_code)
        self.assertIn("exported contacts=3", output)
        self.assertIn("index=", output)
        self.assertIn("report=", output)
        self.assertIn("# 人脉索引", people_index_text)
        self.assertIn("## 优先跟进", people_index_text)
        self.assertIn(
            "1. [[群成员A|群成员A]] / 项目跟进 / 50分 / 中（有明确关系信号，适合跟进）",
            people_index_text,
        )
        self.assertIn("   - 草稿：群成员A，上次你在「项目交流群（3）」里提到", people_index_text)
        self.assertLess(people_index_text.index("## 优先跟进"), people_index_text.index("## 最近联系人"))
        self.assertIn(
            "- [[陈明 DANIEL|陈明 DANIEL]]（私聊/单聊，2026-05-26 22:22）：机构/公司：示例资本；身份线索：陈明, Daniel Chen",
            people_index_text,
        )
        self.assertIn(
            "- [[群成员A|群成员A]]（群内联系人，2026-05-26 22:21）：来源：[[项目交流群（3）|项目交流群（3）]]；关系信号：项目/合作；资料缺口：缺少身份/机构线索（建议补充：公司/职位/角色、认识场景）",
            people_index_text,
        )
        self.assertIn("# 群成员A", sunny_text)
        self.assertIn("类型：群内联系人", sunny_text)
        self.assertIn("来源群/会话：[[项目交流群（3）|项目交流群（3）]]", sunny_text)
        self.assertIn("## 资料缺口", sunny_text)
        self.assertIn("- 缺少身份/机构线索（建议补充：公司/职位/角色、认识场景）", sunny_text)
        self.assertIn("草稿：群成员A，上次你在「项目交流群（3）」里提到", sunny_text)
        self.assertIn("近期发言人：[[群成员A|群成员A]]", group_text)
        self.assertNotIn("## 资料缺口", group_text)
        self.assertIn("# 陈明 DANIEL", daniel_text)
        self.assertIn("机构/公司：示例资本", daniel_text)
        self.assertNotIn("## 资料缺口", daniel_text)
        self.assertIn("# 社交圈分析报告 2026-05-27", report_text)
        self.assertIn("## 人脉分析", report_text)
        self.assertIn("联系人档案：3", report_text)
        self.assertIn("### 有关系信号的人脉", report_text)
        self.assertIn("- [[群成员A|群成员A]]：项目/合作", report_text)
        self.assertIn("- [[项目交流群（3）|项目交流群（3）]]：项目/合作", report_text)
        self.assertIn("### 最近出现的人脉", report_text)
        self.assertIn("- [[陈明 DANIEL|陈明 DANIEL]]（私聊/单聊，2026-05-26 22:22）", report_text)
        self.assertIn(
            "- [[群成员A|群成员A]]（群内联系人，来源：[[项目交流群（3）|项目交流群（3）]]，2026-05-26 22:21）",
            report_text,
        )
        self.assertIn("### 需要补充信息的人脉", report_text)
        self.assertIn(
            "- [[群成员A|群成员A]]（群内联系人）：缺少身份/机构线索（建议补充：公司/职位/角色、认识场景）；最近出现 2026-05-26 22:21",
            report_text,
        )
        self.assertNotIn(
            "- [[项目交流群（3）|项目交流群（3）]]（群聊）：缺少身份/机构线索",
            report_text,
        )
        self.assertIn("## 应该主动联系的人", report_text)
        self.assertIn("[[群成员A|群成员A]] / 项目跟进 / 50分", report_text)
        self.assertIn("草稿：群成员A，上次你在「项目交流群（3）」里提到", report_text)

    def test_obsidian_export_rejects_report_date_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            vault = root / "Obsidian Vault"
            init_db(db_path)

            with self.assertRaisesRegex(SystemExit, "--date"):
                main(
                    [
                        "--db",
                        str(db_path),
                        "export-obsidian",
                        "--vault",
                        str(vault),
                        "--date",
                        "../人脉/索引",
                    ]
                )

            self.assertFalse((vault / "社交圈").exists())

    def test_obsidian_export_disambiguates_sanitized_filename_collisions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            vault = root / "Obsidian Vault"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="A/B\n最近看到一个想法。",
                contact_hint="A/B",
                source="test",
                captured_at="2026-05-26T22:21:20+08:00",
            )
            ingest_capture(
                db_path,
                raw_text="A:B\n下周方便聊聊吗？",
                contact_hint="A:B",
                source="test",
                captured_at="2026-05-26T22:22:20+08:00",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "export-obsidian",
                        "--vault",
                        str(vault),
                        "--date",
                        "2026-05-27",
                    ]
                )

            people_dir = vault / "社交圈" / "人脉"
            first_path = people_dir / "A-B.md"
            second_path = people_dir / "A-B-2.md"
            first_exists = first_path.exists()
            second_exists = second_path.exists()
            first_text = first_path.read_text(encoding="utf-8")
            second_text = second_path.read_text(encoding="utf-8")
            index_text = (people_dir / "索引.md").read_text(encoding="utf-8")

        self.assertEqual(0, exit_code)
        self.assertIn("exported contacts=2", stdout.getvalue())
        self.assertTrue(first_exists)
        self.assertTrue(second_exists)
        self.assertIn("# A/B", first_text)
        self.assertIn("# A:B", second_text)
        self.assertIn("[[A-B|A/B]]", index_text)
        self.assertIn("[[A-B-2|A:B]]", index_text)


if __name__ == "__main__":
    unittest.main()
