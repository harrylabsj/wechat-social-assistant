import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wsa.connectors import (
    CaptureRequest,
    MacOSAccessibilityConnector,
    _parse_accessibility_output,
    capture_connector,
    connector_statuses,
    text_connector,
)
from wsa.security import PathPolicyError, resolve_mcp_path


class SecurityAndConnectorTests(unittest.TestCase):
    def test_mcp_path_policy_rejects_escape_after_resolution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "trusted"
            root.mkdir()
            inside = root / "data" / "social.db"
            outside = Path(tmpdir) / "secret.db"
            with patch.dict(
                os.environ,
                {"WSA_MCP_ENFORCE_PATHS": "1", "WSA_ALLOWED_ROOT": str(root)},
                clear=False,
            ):
                self.assertEqual(inside.resolve(), resolve_mcp_path(inside, default=inside, label="db_path"))
                with self.assertRaises(PathPolicyError):
                    resolve_mcp_path(outside, default=inside, label="db_path")
                link = root / "link"
                link.symlink_to(Path(tmpdir) / "escaped", target_is_directory=False)
                with self.assertRaises(PathPolicyError):
                    resolve_mcp_path(link / "social.db", default=inside, label="db_path")

    def test_unenforced_python_api_remains_flexible_for_explicit_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "social.db"
            with patch.dict(os.environ, {"WSA_MCP_ENFORCE_PATHS": "0"}, clear=False):
                self.assertEqual(path.resolve(), resolve_mcp_path(path, default=path, label="db_path"))

    def test_connector_selection_and_status_are_explicit(self):
        self.assertEqual("macos-window-capture", capture_connector("window").name)
        self.assertEqual("macos-screen-capture", capture_connector("screen").name)
        with self.assertRaises(ValueError):
            capture_connector("private-db")
        statuses = connector_statuses()
        self.assertEqual({"macos-window-capture", "macos-screen-capture", "macos-accessibility"}, {item.name for item in statuses})
        self.assertIsInstance(MacOSAccessibilityConnector().status().detail, str)
        self.assertEqual("macos-accessibility", text_connector().name)

    def test_accessibility_jsonl_maps_to_deduplicated_observations(self):
        capture = _parse_accessibility_output(
            '{"kind":"meta","app_name":"WeChat","window_title":"张三"}\n'
            '{"kind":"text","text":"张三","confidence":1,"bbox":{"x":0.1,"y":0.2,"width":0.3,"height":0.04},"role":"AXStaticText"}\n'
            '{"kind":"text","text":"张三","confidence":1,"bbox":{"x":0.1,"y":0.2,"width":0.3,"height":0.04},"role":"AXStaticText"}\n'
            '{"kind":"text","text":"你好，最近怎么样？","confidence":1,"role":"AXStaticText"}\n'
        )

        self.assertEqual("WeChat", capture.app_name)
        self.assertEqual("张三", capture.window_title)
        self.assertEqual("张三\n你好，最近怎么样？", capture.text)
        self.assertEqual(2, len(capture.observations))
        self.assertEqual("accessibility", capture.observations[0].source)
        self.assertEqual((0.1, 0.2, 0.3, 0.04), capture.observations[0].bbox)
        self.assertEqual((0, 1), tuple(item.sequence for item in capture.observations))

    def test_accessibility_parser_keeps_identical_unbounded_messages(self):
        capture = _parse_accessibility_output(
            '{"kind":"text","text":"好的","role":"AXStaticText"}\n'
            '{"kind":"text","text":"好的","role":"AXStaticText"}\n'
        )

        self.assertEqual(["好的", "好的"], [item.text for item in capture.observations])

    def test_capture_request_is_structured(self):
        request = CaptureRequest(Path("/tmp/capture.png"), mode="window", crop_preset="wechat-chat")
        self.assertEqual("window", request.mode)
        self.assertEqual("wechat-chat", request.crop_preset)


if __name__ == "__main__":
    unittest.main()
