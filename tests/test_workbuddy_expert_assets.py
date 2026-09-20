import _env_guard  # noqa: F401 - scrub inherited WSA_* before importing wsa

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXPERT_ROOT = ROOT / "agent" / "workbuddy" / "wechat-social-assistant-expert"


class WorkBuddyExpertAssetTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(
            (EXPERT_ROOT / ".codebuddy-plugin" / "plugin.json").read_text(encoding="utf-8")
        )

    def test_market_metadata_matches_the_confirmed_expert(self):
        self.assertEqual("wechat-social-assistant-expert", self.manifest["name"])
        self.assertEqual("海纳·社交专家", self.manifest["displayName"]["zh"])
        self.assertEqual("微信社交助手", self.manifest["profession"]["zh"])
        self.assertEqual(
            self.manifest["defaultInitPrompt"]["zh"],
            self.manifest["quickPrompts"][0]["zh"],
        )
        self.assertEqual(3, len(self.manifest["tags"]))
        self.assertEqual(3, len(self.manifest["quickPrompts"]))

    def test_expert_links_agent_skills_avatar_and_connector(self):
        self.assertEqual(["oc_a3f7d4a2da76c7cd"], self.manifest["dependencies"]["connectors"])
        agent = EXPERT_ROOT / "agents" / "wechat-social-assistant.md"
        avatar = EXPERT_ROOT / self.manifest["avatar"]
        self.assertTrue(agent.exists())
        self.assertTrue(avatar.exists())
        self.assertEqual(b"\x89PNG\r\n\x1a\n", avatar.read_bytes()[:8])
        for path in self.manifest["skills"]:
            self.assertTrue((EXPERT_ROOT / path / "SKILL.md").exists(), path)

    def test_expert_keeps_local_and_user_review_boundaries(self):
        text = (EXPERT_ROOT / "agents" / "wechat-social-assistant.md").read_text(encoding="utf-8")
        self.assertIn("不自动发送微信消息", text)
        self.assertIn("不读取或修改微信私有数据库", text)
        self.assertIn("用户明确同意", text)


if __name__ == "__main__":
    unittest.main()
