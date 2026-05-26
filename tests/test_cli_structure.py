import ast
import unittest
from collections import Counter
from pathlib import Path


class CliStructureTests(unittest.TestCase):
    def test_cli_module_does_not_define_duplicate_functions(self):
        cli_path = Path(__file__).parents[1] / "wsa" / "cli.py"
        tree = ast.parse(cli_path.read_text(encoding="utf-8"))

        function_names = [
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        duplicates = sorted(
            name
            for name, count in Counter(function_names).items()
            if count > 1
        )

        self.assertEqual([], duplicates)


if __name__ == "__main__":
    unittest.main()
