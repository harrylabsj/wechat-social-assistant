import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AgentAssetTests(unittest.TestCase):
    def test_agent_manifest_declares_mcp_and_openclaw_plugin(self):
        manifest = json.loads((ROOT / "agent" / "agent.json").read_text(encoding="utf-8"))
        self.assertIn("openclaw-plugin", manifest["ecosystems"])
        self.assertEqual(
            "agent/openclaw/wechat-social-assistant-plugin/openclaw.plugin.json",
            manifest["openclaw_plugin"]["manifest"],
        )
        self.assertTrue((ROOT / manifest["openclaw_plugin"]["entrypoint"]).exists())

    def test_openclaw_plugin_manifest_and_package_are_self_contained(self):
        plugin_root = ROOT / "agent" / "openclaw" / "wechat-social-assistant-plugin"
        manifest = json.loads((plugin_root / "openclaw.plugin.json").read_text(encoding="utf-8"))
        package = json.loads((plugin_root / "package.json").read_text(encoding="utf-8"))

        self.assertEqual("wechat-social-assistant", manifest["id"])
        self.assertIn("wsa_capture_observations", manifest["contracts"]["tools"])
        self.assertIn("wsa_ocr_reviews", manifest["contracts"]["tools"])
        self.assertIn("wsa_record_ocr_review", manifest["contracts"]["tools"])
        self.assertEqual("wechat-social-assistant", package["name"])
        self.assertEqual("./index.js", package["openclaw"]["extensions"][0])
        self.assertTrue((plugin_root / "index.js").exists())
        self.assertTrue((plugin_root / "openclaw_compat.js").exists())
        self.assertEqual(["./skills"], manifest["skills"])
        self.assertTrue((plugin_root / "skills" / "wechat-social-assistant" / "SKILL.md").exists())

    def test_native_helpers_are_included_for_wheel_builds(self):
        native_root = ROOT / "wsa" / "native"
        for name in (
            "macos_ocr.swift",
            "macos_frontmost_app.swift",
            "macos_frontmost_window.swift",
            "macos_accessibility_probe.swift",
        ):
            self.assertTrue((native_root / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
