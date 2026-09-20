"""``mcp_server`` reuses private helpers from ``cli``; keep that contract honest.

The two front ends deliberately share one view layer instead of duplicating
rendering and filtering.  The cost is that a private name in ``cli`` is really
a shared surface: renaming or resiting one breaks the MCP server at request
time, where nothing would notice until a tool call fails.

This test reads the actual import statement in ``mcp_server`` and checks the
surface, so it stays in sync automatically -- adding a new shared helper
extends the contract without touching this file.
"""

import _env_guard  # noqa: F401 - scrub inherited WSA_* before importing wsa

import ast
import inspect
import unittest
from pathlib import Path

from wsa import cli, mcp_server


def _names_imported_from_cli() -> list[str]:
    source = Path(inspect.getfile(mcp_server)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "cli" and node.level == 1:
            names.extend(alias.name for alias in node.names)
    return names


class SharedViewSurfaceTests(unittest.TestCase):
    def test_mcp_server_imports_a_documented_surface_from_cli(self):
        names = _names_imported_from_cli()

        self.assertTrue(names, "mcp_server no longer imports from cli; update this contract")
        for name in names:
            with self.subTest(name=name):
                self.assertTrue(
                    hasattr(cli, name),
                    f"wsa.cli.{name} is imported by wsa.mcp_server but no longer exists",
                )
                self.assertTrue(callable(getattr(cli, name)), f"wsa.cli.{name} is not callable")

    def test_shared_surface_is_marked_in_cli(self):
        """A reader editing cli.py must be able to see which names MCP depends on."""

        source = Path(inspect.getfile(cli)).read_text(encoding="utf-8")

        self.assertIn("SHARED VIEW SURFACE", source)

    def test_contact_match_normalisation_is_not_duplicated(self):
        """Both front ends must normalise a contact query the same way."""

        self.assertIs(
            mcp_server._normalize_match_text,
            cli._normalize_contact_match_text,
            "mcp_server must reuse cli's normaliser rather than keep a second copy",
        )


if __name__ == "__main__":
    unittest.main()
