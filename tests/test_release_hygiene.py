import unittest
from pathlib import Path

from wsa.cli import DEFAULT_OBSIDIAN_VAULT, build_parser


class ReleaseHygieneTests(unittest.TestCase):
    def test_default_obsidian_vault_is_portable(self):
        expected = Path.home() / "Documents" / "Obsidian Vault"

        self.assertEqual(expected, DEFAULT_OBSIDIAN_VAULT)
        args = build_parser().parse_args(["export-obsidian"])
        self.assertEqual(expected, args.vault)

    def test_release_files_do_not_expose_private_data_by_default(self):
        root = Path(__file__).parents[1]
        readme = (root / "README.md").read_text(encoding="utf-8")
        gitignore = (root / ".gitignore").read_text(encoding="utf-8")

        self.assertNotIn("/Users/jianghaidong", readme)
        self.assertNotIn("openclawhaidong", readme)
        project_text = "\n".join(
            path.read_text(encoding="utf-8")
            for folder in ("README.md", "docs", "tests", "wsa")
            for path in ([root / folder] if (root / folder).is_file() else sorted((root / folder).glob("*.py")) + sorted((root / folder).glob("*.md")))
            if path.name != "test_release_hygiene.py"
        )
        for private_fixture in (
            "咖特思",
            "Sunny",
            "宏宇",
            "陆宏宇",
            "Daniel Lu",
            "德同资本",
            "邸颖",
            "edatec.cn",
        ):
            self.assertNotIn(private_fixture, project_text)
        for pattern in (
            ".DS_Store",
            "__pycache__/",
            "*.py[cod]",
            "bin/",
            "data/",
            "reports/",
        ):
            self.assertIn(pattern, gitignore)


if __name__ == "__main__":
    unittest.main()
