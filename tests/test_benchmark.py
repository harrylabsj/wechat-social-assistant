import json
import unittest
from pathlib import Path

from wsa.benchmark import (
    DEFAULT_FIXTURE_DIR,
    benchmark_report_to_dict,
    run_perception_benchmark,
)


class PerceptionBenchmarkTests(unittest.TestCase):
    def test_privacy_safe_fixtures_pass_with_perfect_baseline(self):
        report = run_perception_benchmark(DEFAULT_FIXTURE_DIR)

        self.assertTrue(report.passed)
        self.assertEqual(1.0, report.text_precision)
        self.assertEqual(1.0, report.text_recall)
        self.assertEqual(1.0, report.speaker_precision)
        self.assertEqual(1.0, report.speaker_recall)
        self.assertEqual(2, len(report.cases))
        self.assertEqual(str(DEFAULT_FIXTURE_DIR), benchmark_report_to_dict(report)["fixture_dir"])

    def test_fixture_manifest_is_json_and_contains_no_private_paths(self):
        manifest = Path(DEFAULT_FIXTURE_DIR) / "ax_cases.json"
        payload = json.loads(manifest.read_text(encoding="utf-8"))

        self.assertEqual(1, payload["schema_version"])
        self.assertNotIn("/Users/", manifest.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
