import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from wsa import mcp_server
from wsa.store import ingest_capture, init_db


ROOT = Path(__file__).resolve().parents[1]


class MCPServerContractTests(unittest.TestCase):
    def test_declares_read_only_tools_resources_and_prompts(self):
        tool_names = [tool["name"] for tool in mcp_server.MCP_TOOLS]

        self.assertEqual(
            [
                "get_status",
                "get_audit_report",
                "search_contacts",
                "get_contact_brief",
                "get_next_followup",
                "get_daily_report",
                "get_weekly_report",
                "get_relationship_quality",
                "get_relationship_dashboard",
                "list_relationship_sources",
                "list_relationship_candidates",
                "confirm_relationship_candidate",
                "list_feedback",
                "record_feedback",
                "list_recent_captures",
                "get_capture_observations",
            ],
            tool_names,
        )
        self.assertFalse(
            {
                "watch",
                "capture",
                "import_image",
                "reset",
                "analyze",
                "export_obsidian",
                "mark_done",
            }.intersection(tool_names)
        )
        for tool in mcp_server.MCP_TOOLS:
            self.assertEqual("object", tool["inputSchema"]["type"])
            self.assertIn("description", tool)

        self.assertGreaterEqual(
            {resource["uri"] for resource in mcp_server.MCP_RESOURCES},
            {"wsa://status", "wsa://contacts", "wsa://daily-report", "wsa://relationship-quality"},
        )
        self.assertGreaterEqual(
            {prompt["name"] for prompt in mcp_server.MCP_PROMPTS},
            {"daily-relationship-review", "weekly-relationship-review", "contact-followup", "safe-capture-review"},
        )

    def test_jsonrpc_initializes_and_lists_capabilities(self):
        initialized = mcp_server.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
        tools = mcp_server.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        )
        prompts = mcp_server.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 3, "method": "prompts/list", "params": {}}
        )
        resources = mcp_server.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 4, "method": "resources/list", "params": {}}
        )
        missing = mcp_server.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 5, "method": "missing/method", "params": {}}
        )

        result = initialized["result"]
        self.assertEqual("2.0", initialized["jsonrpc"])
        self.assertEqual(mcp_server.MCP_PROTOCOL_VERSION, result["protocolVersion"])
        self.assertEqual("wechat-social-assistant", result["serverInfo"]["name"])
        self.assertIn("tools", result["capabilities"])
        self.assertIn("resources", result["capabilities"])
        self.assertIn("prompts", result["capabilities"])
        self.assertEqual(mcp_server.MCP_TOOLS, tools["result"]["tools"])
        self.assertEqual(mcp_server.MCP_PROMPTS, prompts["result"]["prompts"])
        self.assertEqual(mcp_server.MCP_RESOURCES, resources["result"]["resources"])
        self.assertEqual(-32601, missing["error"]["code"])

    def test_read_only_tool_calls_return_structured_relationship_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            captures_dir = root / "data" / "captures"
            captures_dir.mkdir(parents=True)
            (captures_dir / "wechat-1.png").write_bytes(b"png")
            _seed_relationship_data(db_path)

            status = _call_tool("get_status", db_path=db_path, captures_dir=captures_dir)
            audit = _call_tool("get_audit_report", db_path=db_path)
            search = _call_tool("search_contacts", db_path=db_path, query="张三")
            brief = _call_tool("get_contact_brief", db_path=db_path, contact_name="张三")
            followup = _call_tool("get_next_followup", db_path=db_path, contact_name="张三", min_score=0)
            daily = _call_tool("get_daily_report", db_path=db_path, date="2026-05-27", min_score=0)
            weekly = _call_tool("get_weekly_report", db_path=db_path, date="2026-05-27", min_score=0)
            quality = _call_tool("get_relationship_quality", db_path=db_path, contact_name="张三", min_score=0)
            dashboard = _call_tool("get_relationship_dashboard", db_path=db_path, date="2026-05-27", min_score=0)
            sources = _call_tool("list_relationship_sources", db_path=db_path, contact_name="张三")
            candidates = _call_tool("list_relationship_candidates", db_path=db_path, min_confidence=0)
            feedback = _call_tool("list_feedback", db_path=db_path, contact_name="张三")
            recent = _call_tool("list_recent_captures", db_path=db_path, limit=2)
            observations = _call_tool("get_capture_observations", db_path=db_path, capture_id=1)

        self.assertGreaterEqual(status["structuredContent"]["contact_count"], 3)
        self.assertIn("audit", audit["structuredContent"])
        self.assertIn("# 本地数据审计", audit["content"][0]["text"])
        self.assertEqual(1, status["structuredContent"]["screenshot_count"])
        self.assertEqual("张三", search["structuredContent"]["contacts"][0]["name"])
        self.assertIn("增长交流群（3）", search["structuredContent"]["contacts"][0]["source_chats"])
        self.assertIn("# 联系人简报：张三", brief["content"][0]["text"])
        self.assertEqual("张三", brief["structuredContent"]["profile"]["name"])
        self.assertEqual("张三", followup["structuredContent"]["suggestion"]["person_name"])
        self.assertIn("draft", followup["structuredContent"]["suggestion"])
        self.assertIn("# 社交圈分析报告 2026-05-27", daily["content"][0]["text"])
        self.assertIn("followups", daily["structuredContent"])
        self.assertIn("# 社交圈周报 2026-W22", weekly["content"][0]["text"])
        self.assertEqual("2026-W22", weekly["structuredContent"]["week"])
        self.assertIn("# 关系运营台", quality["content"][0]["text"])
        self.assertIn("# 关系驾驶舱", dashboard["content"][0]["text"])
        self.assertIn("dashboard", dashboard["structuredContent"])
        self.assertIn("sources", sources["structuredContent"])
        self.assertEqual("张三", quality["structuredContent"]["cards"][0]["name"])
        self.assertIn("relationship_strength", quality["structuredContent"]["cards"][0]["scores"])
        self.assertTrue(quality["structuredContent"]["cards"][0]["scores"]["relationship_strength"]["evidence"])
        self.assertIn("张三", {candidate["name"] for candidate in candidates["structuredContent"]["candidates"]})
        self.assertIn("# 人脉候选人", candidates["content"][0]["text"])
        self.assertEqual([], feedback["structuredContent"]["feedback"])
        self.assertEqual(2, len(recent["structuredContent"]["captures"]))
        self.assertEqual("增长交流群（3）", recent["structuredContent"]["captures"][0]["contact_name"])
        self.assertEqual(1, observations["structuredContent"]["capture_id"])
        self.assertTrue(observations["structuredContent"]["observations"])
        self.assertIn("bbox", observations["structuredContent"]["observations"][0])

    def test_resources_and_prompts_are_readable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_relationship_data(db_path)

            status = mcp_server.handle_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "resources/read",
                    "params": {"uri": "wsa://status", "arguments": {"db_path": str(db_path)}},
                }
            )
            audit = mcp_server.handle_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "resources/read",
                    "params": {"uri": "wsa://audit", "arguments": {"db_path": str(db_path)}},
                }
            )
            prompt = mcp_server.handle_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "prompts/get",
                    "params": {
                        "name": "contact-followup",
                        "arguments": {"contact_name": "张三"},
                    },
                }
            )
            quality = mcp_server.handle_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "resources/read",
                    "params": {"uri": "wsa://relationship-quality", "arguments": {"db_path": str(db_path)}},
                }
            )
            dashboard = mcp_server.handle_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "resources/read",
                    "params": {"uri": "wsa://relationship-dashboard", "arguments": {"db_path": str(db_path)}},
                }
            )

        self.assertEqual("wsa://status", status["result"]["contents"][0]["uri"])
        self.assertEqual("wsa://audit", audit["result"]["contents"][0]["uri"])
        self.assertIn("# 本地数据审计", audit["result"]["contents"][0]["text"])
        self.assertIn("# WeChat Social Assistant Status", status["result"]["contents"][0]["text"])
        self.assertIn("张三", prompt["result"]["messages"][0]["content"]["text"])
        self.assertIn("只读", prompt["result"]["messages"][0]["content"]["text"])
        self.assertEqual("wsa://relationship-quality", quality["result"]["contents"][0]["uri"])
        self.assertIn("# 关系运营台", quality["result"]["contents"][0]["text"])
        self.assertEqual("wsa://relationship-dashboard", dashboard["result"]["contents"][0]["uri"])
        self.assertIn("# 关系驾驶舱", dashboard["result"]["contents"][0]["text"])

    def test_record_feedback_mcp_tool_requires_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_relationship_data(db_path)

            rejected = mcp_server.handle_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "record_feedback",
                        "arguments": {
                            "db_path": str(db_path),
                            "contact_name": "张三",
                            "action": "too_pushy",
                        },
                    },
                }
            )
            accepted = _call_tool(
                "record_feedback",
                db_path=db_path,
                contact_name="张三",
                action="too_pushy",
                note="语气太主动",
                confirmed=True,
                confirmation_text="record local feedback",
                created_at="2026-05-27T10:00:00+08:00",
            )
            listed = _call_tool("list_feedback", db_path=db_path, contact_name="张三")

        self.assertEqual(-32602, rejected["error"]["code"])
        self.assertEqual("too_pushy", accepted["structuredContent"]["feedback"]["action"])
        self.assertEqual("张三", listed["structuredContent"]["feedback"][0]["person_name"])

    def test_record_feedback_mcp_tool_rejects_invalid_until(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_relationship_data(db_path)

            rejected = mcp_server.handle_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "record_feedback",
                        "arguments": {
                            "db_path": str(db_path),
                            "contact_name": "张三",
                            "action": "snooze",
                            "until_at": "tomorrow",
                            "confirmed": True,
                            "confirmation_text": "record local feedback",
                        },
                    },
                }
            )
            listed = _call_tool("list_feedback", db_path=db_path, contact_name="张三")

        self.assertEqual(-32602, rejected["error"]["code"])
        self.assertIn("invalid ISO timestamp or date", rejected["error"]["message"])
        self.assertEqual([], listed["structuredContent"]["feedback"])

    def test_confirm_candidate_mcp_tool_requires_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "social.db"
            _seed_relationship_data(db_path)

            rejected = mcp_server.handle_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "confirm_relationship_candidate",
                        "arguments": {
                            "db_path": str(db_path),
                            "name": "张三",
                            "source_chat": "增长交流群（3）",
                        },
                    },
                }
            )
            accepted = _call_tool(
                "confirm_relationship_candidate",
                db_path=db_path,
                name="张三",
                source_chat="增长交流群（3）",
                confirmed=True,
                confirmation_text="confirm relationship candidate",
                confirmed_at="2026-05-27T10:00:00+08:00",
                note="值得线下认识",
            )

        self.assertEqual(-32602, rejected["error"]["code"])
        self.assertEqual("confirmed", accepted["structuredContent"]["candidate"]["status"])
        self.assertEqual("张三", accepted["structuredContent"]["candidate"]["name"])

    def test_module_cli_help_is_available(self):
        result = subprocess.run(
            [sys.executable, "-m", "wsa.mcp_server", "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("stdio", result.stdout)
        self.assertIn("MCP", result.stdout)


def _call_tool(tool_name: str, *, db_path: Path, **arguments):
    payload = mcp_server.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": {"db_path": str(db_path), **arguments}},
        }
    )
    if "error" in payload:
        raise AssertionError(payload["error"])
    return payload["result"]


def _seed_relationship_data(db_path: Path) -> None:
    init_db(db_path)
    ingest_capture(
        db_path,
        raw_text=(
            "增长交流群（3）\n"
            "张三\n"
            "我是星火科技的张三，最近在做AI社交助手，需要看看是否有合作机会？\n"
            "李四\n"
            "谢谢分享，可以下周聊一下。"
        ),
        contact_hint="增长交流群（3）",
        source="test",
        captured_at="2026-05-27T09:00:00+08:00",
    )
    ingest_capture(
        db_path,
        raw_text="王五\n王五老师，谢谢你上次推荐的文章，我整理了一版方案，需要你看看。",
        contact_hint="王五",
        source="test",
        captured_at="2026-05-26T18:30:00+08:00",
    )


if __name__ == "__main__":
    unittest.main()
