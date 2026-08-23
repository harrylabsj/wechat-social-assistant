import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wsa.connectors import (
    CaptureRequest,
    MacOSAccessibilityConnector,
    TextCapture,
    _parse_accessibility_output,
    capture_connector,
    connector_statuses,
    merge_text_captures,
    text_connector,
)
from wsa.observations import OCRObservation
from wsa.perception import annotate_accessibility_speakers, explicit_speaker_label
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
            '{"kind":"text","text":"张三","confidence":1,"bbox":{"x":0.1,"y":0.2,"width":0.3,"height":0.04},"role":"AXStaticText","path":"0.1.0","parent_path":"0.1","depth":3}\n'
            '{"kind":"text","text":"张三","confidence":1,"bbox":{"x":0.1,"y":0.2,"width":0.3,"height":0.04},"role":"AXStaticText"}\n'
            '{"kind":"text","text":"你好，最近怎么样？","confidence":1,"role":"AXStaticText"}\n'
        )

        self.assertEqual("WeChat", capture.app_name)
        self.assertEqual("张三", capture.window_title)
        self.assertEqual("张三\n你好，最近怎么样？", capture.text)
        self.assertEqual(2, len(capture.observations))
        self.assertEqual("accessibility", capture.observations[0].source)
        self.assertEqual((0.1, 0.2, 0.3, 0.04), capture.observations[0].bbox)
        self.assertEqual("AXStaticText", capture.observations[0].role)
        self.assertEqual("0.1.0", capture.observations[0].node_path)
        self.assertEqual("0.1", capture.observations[0].parent_path)
        self.assertEqual(3, capture.observations[0].depth)
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

    def test_explicit_accessibility_label_is_conservative_and_attaches_to_message(self):
        observations = (
            OCRObservation(
                text="张三:",
                confidence=1.0,
                bbox_x=0.2,
                bbox_y=0.72,
                bbox_width=0.12,
                bbox_height=0.04,
                parent_path="0.4",
            ),
            OCRObservation(
                text="明天一起吃饭吗？",
                confidence=1.0,
                bbox_x=0.2,
                bbox_y=0.62,
                bbox_width=0.3,
                bbox_height=0.06,
                parent_path="0.4",
            ),
        )

        annotated = annotate_accessibility_speakers(observations)

        self.assertEqual("张三", explicit_speaker_label("张三:"))
        self.assertIsNone(explicit_speaker_label("项目方向:"))
        self.assertIsNone(annotated[0].speaker_candidate)
        self.assertEqual("张三", annotated[1].speaker_candidate)
        self.assertEqual(0.65, annotated[1].speaker_confidence)

    def test_accessibility_label_without_structure_or_geometry_is_not_attributed(self):
        observations = (
            OCRObservation(text="张三:"),
            OCRObservation(text="明天一起吃饭吗？"),
        )

        annotated = annotate_accessibility_speakers(observations)

        self.assertIsNone(annotated[1].speaker_candidate)

    def test_merge_text_captures_keeps_stable_occurrences_and_drops_transient_text(self):
        first = TextCapture(
            text="张三\n稳定消息\n正在输入",
            observations=(
                OCRObservation(text="张三", bbox_x=0.1, bbox_y=0.8, bbox_width=0.1, bbox_height=0.03),
                OCRObservation(text="稳定消息", bbox_x=0.2, bbox_y=0.5, bbox_width=0.2, bbox_height=0.05),
                OCRObservation(text="正在输入", bbox_x=0.2, bbox_y=0.4, bbox_width=0.2, bbox_height=0.05),
            ),
        )
        second = TextCapture(
            text="张三\n稳定消息",
            observations=(
                OCRObservation(text="张三", bbox_x=0.101, bbox_y=0.8, bbox_width=0.1, bbox_height=0.03),
                OCRObservation(text="稳定消息", bbox_x=0.2, bbox_y=0.5, bbox_width=0.2, bbox_height=0.05),
            ),
        )

        merged = merge_text_captures((first, second), min_stable_frames=2)

        self.assertEqual(["张三", "稳定消息"], [item.text for item in merged.observations])
        self.assertEqual(2, merged.frame_count)
        self.assertGreater(merged.stability, 0.0)


if __name__ == "__main__":
    unittest.main()
