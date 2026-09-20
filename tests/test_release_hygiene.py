"""Guard the public release against shipping private data.

Two rules, deliberately different in kind:

* A **positive** rule: every contact name used as a test fixture must appear
  in ``ALLOWED_FIXTURE_NAMES`` below.  Adding a fixture name is therefore a
  visible, reviewable edit.  A denylist can only remove names somebody
  already noticed; this is what stops the next real contact name from being
  pasted into a regression test.
* An optional **negative** rule: terms listed in ``.private-denylist`` (git
  ignored, one term per line) must not appear anywhere in the tree.  The
  list stays out of the repository on purpose -- an in-repo list of "names
  that must never be published" publishes exactly those names.
"""

import _env_guard  # noqa: F401 - scrub inherited WSA_* before importing wsa

import re
import unittest
from pathlib import Path

from wsa.cli import DEFAULT_OBSIDIAN_VAULT, build_parser


ROOT = Path(__file__).parents[1]
DENYLIST_FILE = ROOT / ".private-denylist"

SCANNED_TREES = ("wsa", "tests", "docs", "agent")
SCANNED_FILES = ("README.md", "CHANGELOG.md", "SECURITY.md")
SCANNED_SUFFIXES = {".py", ".md", ".json", ".js", ".yaml", ".yml", ".txt", ".swift", ".sh"}

FIXTURE_NAME_RE = re.compile(r'(?:contact_hint|contact_name|person_name)="([^"]*)"')

# Obvious placeholders only: the 张三/李四/王五/赵六/孙七/钱八 sequence, generic
# role labels, UI strings the parser must reject, and synthetic group names.
ALLOWED_FIXTURE_NAMES = frozenset(
    {
        "",
        "A:B",
        "A/B",
        "AI路演群（12）",
        "不存在的人",
        "陈明 DANIEL",
        "李四",
        "联系人B",
        "路由联系人",
        "钱七",
        "孙八",
        "孙七",
        "外部联系人",
        "王五",
        "王志平",
        "微信 文件 编辑",
        "微信会话列表",
        "闲聊群（20）",
        "项目交流群（3）",
        "项目群（2）",
        "医疗AI路演群（6）",
        "增长交流群（3）",
        "张三",
        "赵六",
    }
)


def _scanned_paths() -> list[Path]:
    paths = [ROOT / name for name in SCANNED_FILES]
    for tree in SCANNED_TREES:
        directory = ROOT / tree
        if not directory.is_dir():
            continue
        paths.extend(
            path
            for path in directory.rglob("*")
            if path.is_file()
            and path.suffix.lower() in SCANNED_SUFFIXES
            and "__pycache__" not in path.parts
        )
    return [path for path in paths if path.is_file() and path.name != Path(__file__).name]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


class ReleaseHygieneTests(unittest.TestCase):
    def test_default_obsidian_vault_is_portable(self):
        expected = Path.home() / "Documents" / "Obsidian Vault"

        self.assertEqual(expected, DEFAULT_OBSIDIAN_VAULT)
        args = build_parser().parse_args(["export-obsidian"])
        self.assertEqual(expected, args.vault)

    def test_fixture_contact_names_are_declared_placeholders(self):
        offenders: dict[str, list[str]] = {}
        for path in (ROOT / "tests").rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            for name in FIXTURE_NAME_RE.findall(_read(path)):
                if name.strip() and name not in ALLOWED_FIXTURE_NAMES:
                    offenders.setdefault(name, []).append(str(path.relative_to(ROOT)))

        self.assertEqual(
            {},
            offenders,
            "Test fixtures may only use declared placeholder names. Add the name to "
            "ALLOWED_FIXTURE_NAMES only after confirming it is not a real contact.",
        )

    def test_release_files_do_not_expose_private_terms(self):
        if not DENYLIST_FILE.is_file():
            self.skipTest(
                f"no {DENYLIST_FILE.name}; create it (git ignored, one term per line) "
                "to check this checkout against your own private terms"
            )
        terms = [
            line.strip()
            for line in DENYLIST_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        self.assertTrue(terms, f"{DENYLIST_FILE.name} is empty")

        hits: dict[str, list[str]] = {}
        for path in _scanned_paths():
            text = _read(path)
            for term in terms:
                if term in text:
                    hits.setdefault(term, []).append(str(path.relative_to(ROOT)))

        self.assertEqual({}, hits, "private terms found in files that ship publicly")

    def test_gitignore_covers_local_data_and_the_private_denylist(self):
        gitignore = _read(ROOT / ".gitignore")

        for pattern in (
            ".DS_Store",
            "__pycache__/",
            "*.py[cod]",
            "bin/",
            "data/",
            "reports/",
            ".private-denylist",
        ):
            self.assertIn(pattern, gitignore)

    def test_every_test_module_imports_the_environment_guard(self):
        """A module that skips the guard can resolve the developer's real data."""

        missing = [
            str(path.relative_to(ROOT))
            for path in sorted((ROOT / "tests").glob("test_*.py"))
            if "_env_guard" not in _read(path)
        ]

        self.assertEqual(
            [],
            missing,
            "add `import _env_guard` as the first import of every test module",
        )

    def test_sdist_excludes_the_test_suite(self):
        manifest = _read(ROOT / "MANIFEST.in")

        self.assertIn("prune tests", manifest)


if __name__ == "__main__":
    unittest.main()
