import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
HERMES_SKILL_DIR = AGENT_DIR / "hermes" / "wechat-social-assistant"
PRIVATE_HOME = "/Users/" + "jianghaidong"
PRIVATE_VAULT = "openclaw" + "haidong"


class AgentPackageTests(unittest.TestCase):
    def test_agent_manifest_declares_cross_ecosystem_cli_contract(self):
        manifest_path = AGENT_DIR / "agent.json"

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual("wechat-social-assistant", manifest["id"])
        self.assertEqual("1.1.0", manifest["version"])
        self.assertEqual("python3 -m wsa.cli", manifest["cli"]["entrypoint"])
        self.assertEqual("python3 -m wsa.mcp_server", manifest["mcp"]["command"])
        self.assertEqual("stdio", manifest["mcp"]["transport"])
        self.assertIn("hermes", manifest["ecosystems"])
        self.assertIn("openclaw-non-plugin", manifest["ecosystems"])
        self.assertIn("codex", manifest["ecosystems"])
        self.assertIn("claude-code", manifest["ecosystems"])
        self.assertEqual("local-first", manifest["data_policy"]["storage"])
        self.assertTrue(manifest["data_policy"]["requires_user_confirmation_for_writes"])
        self.assertFalse(manifest["mcp"]["read_only"])
        self.assertTrue(manifest["mcp"]["write_tools_require_confirmation"])
        self.assertIn("get_audit_report", manifest["mcp"]["tools"])
        self.assertIn("get_contact_brief", manifest["mcp"]["tools"])
        self.assertIn("get_relationship_quality", manifest["mcp"]["tools"])
        self.assertIn("get_relationship_dashboard", manifest["mcp"]["tools"])
        self.assertIn("get_weekly_report", manifest["mcp"]["tools"])
        self.assertIn("list_relationship_sources", manifest["mcp"]["tools"])
        self.assertIn("list_relationship_candidates", manifest["mcp"]["tools"])
        self.assertIn("confirm_relationship_candidate", manifest["mcp"]["tools"])
        self.assertIn("list_feedback", manifest["mcp"]["tools"])
        self.assertIn("record_feedback", manifest["mcp"]["tools"])
        self.assertIn("wsa://audit", manifest["mcp"]["resources"])
        self.assertIn("wsa://daily-report", manifest["mcp"]["resources"])
        self.assertIn("wsa://weekly-report", manifest["mcp"]["resources"])
        self.assertIn("wsa://relationship-dashboard", manifest["mcp"]["resources"])
        self.assertIn("wsa://relationship-sources", manifest["mcp"]["resources"])
        self.assertIn("wsa://relationship-quality", manifest["mcp"]["resources"])
        self.assertIn("wsa://relationship-candidates", manifest["mcp"]["resources"])
        self.assertIn("contact-followup", manifest["mcp"]["prompts"])
        self.assertIn("weekly-relationship-review", manifest["mcp"]["prompts"])
        self.assertIn("relationship-candidate-review", manifest["mcp"]["prompts"])

        command_names = {command["name"] for command in manifest["commands"]}
        self.assertGreaterEqual(
            command_names,
            {
                "status",
                "connectors",
                "audit",
                "export-data",
                "delete-contact",
                "contacts",
                "brief",
                "quality",
                "dashboard",
                "cockpit",
                "candidates",
                "candidate-confirm",
                "weekly-report",
                "import-obsidian",
                "sources",
                "import-source",
                "import-wechat-archive",
                "feedback",
                "feedback-list",
                "next",
                "suggest",
                "analyze",
                "export-obsidian",
                "import-image",
                "quick-capture",
                "watch-interval",
                "watch",
                "stop-watch",
            },
        )

    def test_hermes_skill_has_trigger_metadata_and_privacy_guardrails(self):
        skill_path = HERMES_SKILL_DIR / "SKILL.md"

        text = skill_path.read_text(encoding="utf-8")

        self.assertTrue(text.startswith("---\n"))
        self.assertIn("name: wechat-social-assistant", text)
        self.assertIn("description:", text)
        self.assertIn("wsa status", text)
        self.assertIn("wsa-mcp", text)
        self.assertIn("python3 -m wsa.mcp_server", text)
        self.assertIn("wsa quality", text)
        self.assertIn("wsa feedback", text)
        self.assertIn("wsa analyze", text)
        self.assertIn("wsa export-obsidian", text)
        self.assertIn("Never send WeChat messages automatically", text)
        self.assertIn("Do not read or modify WeChat's private databases", text)
        self.assertIn("scripts/doctor.py", text)
        self.assertIn("references/commands.md", text)

    def test_openai_skill_metadata_is_present(self):
        metadata_path = HERMES_SKILL_DIR / "agents" / "openai.yaml"

        text = metadata_path.read_text(encoding="utf-8")

        self.assertIn('display_name: "WeChat Social Assistant"', text)
        self.assertIn('short_description:', text)
        self.assertIn("$wechat-social-assistant", text)
        self.assertIn("allow_implicit_invocation: true", text)

    def test_agent_scripts_are_portable_and_runnable(self):
        doctor = HERMES_SKILL_DIR / "scripts" / "doctor.py"
        runner = HERMES_SKILL_DIR / "scripts" / "wsa_run.py"
        installer = HERMES_SKILL_DIR / "scripts" / "install_cli.sh"

        doctor_result = subprocess.run(
            [sys.executable, str(doctor), "--json", "--project-root", str(ROOT)],
            text=True,
            capture_output=True,
            check=False,
        )
        runner_result = subprocess.run(
            [sys.executable, str(runner), "--list-commands"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, doctor_result.returncode, doctor_result.stderr)
        payload = json.loads(doctor_result.stdout)
        self.assertEqual("wechat-social-assistant", payload["agent_id"])
        self.assertEqual("1.1.0", payload["version"])
        self.assertIn("checks", payload)
        self.assertIn("cli_importable", {check["id"] for check in payload["checks"]})
        self.assertIn("mcp_importable", {check["id"] for check in payload["checks"]})

        self.assertEqual(0, runner_result.returncode, runner_result.stderr)
        self.assertIn("status", runner_result.stdout)
        self.assertIn("audit", runner_result.stdout)
        self.assertIn("export-data", runner_result.stdout)
        self.assertIn("delete-contact", runner_result.stdout)
        self.assertIn("quality", runner_result.stdout)
        self.assertIn("dashboard", runner_result.stdout)
        self.assertIn("cockpit", runner_result.stdout)
        self.assertIn("candidates", runner_result.stdout)
        self.assertIn("candidate-confirm", runner_result.stdout)
        self.assertIn("weekly-report", runner_result.stdout)
        self.assertIn("import-obsidian", runner_result.stdout)
        self.assertIn("sources", runner_result.stdout)
        self.assertIn("import-source", runner_result.stdout)
        self.assertIn("import-wechat-archive", runner_result.stdout)
        self.assertIn("feedback", runner_result.stdout)
        self.assertIn("feedback-list", runner_result.stdout)
        self.assertIn("export-obsidian", runner_result.stdout)
        self.assertIn("quick-capture", runner_result.stdout)
        self.assertIn("watch-interval", runner_result.stdout)

        installer_text = installer.read_text(encoding="utf-8")
        self.assertIn("wechat-social-assistant", installer_text)
        self.assertNotIn(PRIVATE_HOME, installer_text)
        self.assertNotIn(PRIVATE_VAULT, installer_text)

    def test_macos_shortcut_scripts_are_portable(self):
        scripts = {
            "quick": ROOT / "tools" / "wsa-quick-capture.command",
            "interval": ROOT / "tools" / "wsa-set-interval.command",
        }

        for script in scripts.values():
            self.assertTrue(script.exists(), f"missing {script}")
            text = script.read_text(encoding="utf-8")
            self.assertIn("python3 -m wsa.cli", text)
            self.assertNotIn(PRIVATE_HOME, text)
            self.assertNotIn(PRIVATE_VAULT, text)
        self.assertIn("quick-capture", scripts["quick"].read_text(encoding="utf-8"))
        self.assertIn("watch-interval", scripts["interval"].read_text(encoding="utf-8"))

    def test_references_and_openclaw_non_plugin_guide_exist(self):
        expected_paths = [
            HERMES_SKILL_DIR / "references" / "commands.md",
            HERMES_SKILL_DIR / "references" / "privacy.md",
            HERMES_SKILL_DIR / "references" / "workflows.md",
            AGENT_DIR / "openclaw" / "wechat-social-assistant.md",
            ROOT / "docs" / "roadmap.md",
        ]

        for path in expected_paths:
            self.assertTrue(path.exists(), f"missing {path}")
            text = path.read_text(encoding="utf-8")
            self.assertIn("wechat-social-assistant", text)
            self.assertNotIn(PRIVATE_HOME, text)
            self.assertNotIn(PRIVATE_VAULT, text)


if __name__ == "__main__":
    unittest.main()
