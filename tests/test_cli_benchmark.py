import contextlib
import io
import json
import unittest

from wsa.cli import main


class BenchmarkCommandTests(unittest.TestCase):
    def test_perception_benchmark_json_output(self):
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(["benchmark", "perception", "--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertTrue(payload["passed"])
        self.assertEqual(1.0, payload["metrics"]["text_recall"])


if __name__ == "__main__":
    unittest.main()
