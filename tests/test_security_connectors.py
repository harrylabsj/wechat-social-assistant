import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wsa.connectors import CaptureRequest, MacOSAccessibilityConnector, capture_connector, connector_statuses
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

    def test_capture_request_is_structured(self):
        request = CaptureRequest(Path("/tmp/capture.png"), mode="window", crop_preset="wechat-chat")
        self.assertEqual("window", request.mode)
        self.assertEqual("wechat-chat", request.crop_preset)


if __name__ == "__main__":
    unittest.main()
