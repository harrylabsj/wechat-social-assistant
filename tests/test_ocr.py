from pathlib import Path
import subprocess
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from wsa.ocr import (
    CropRegion,
    FrontmostAppStatus,
    capture_screenshot,
    frontmost_app_name,
    frontmost_app_status,
    frontmost_window_id,
    next_capture_path,
    ocr_image,
    _parse_ocr_output,
    parse_crop_spec,
    resolve_crop_region,
)


class FrontmostAppTests(unittest.TestCase):
    def test_parse_structured_ocr_output_keeps_confidence_and_bbox(self):
        observations = _parse_ocr_output(
            '{"text":"群成员A","confidence":0.91,"bbox":{"x":0.1,"y":0.2,"width":0.3,"height":0.04},"source":"vision"}\n'
            "legacy text\n"
        )

        self.assertEqual(["群成员A", "legacy text"], [item.text for item in observations])
        self.assertEqual(0.91, observations[0].confidence)
        self.assertEqual((0.1, 0.2, 0.3, 0.04), observations[0].bbox)
        self.assertEqual("vision-legacy", observations[1].source)

    @patch("wsa.ocr.platform.system", return_value="Darwin")
    @patch("wsa.ocr.ensure_ocr_helper")
    @patch("wsa.ocr.subprocess.run")
    def test_ocr_image_remains_string_compatible_and_exposes_observations(self, run, ensure_helper, system):
        with tempfile.TemporaryDirectory() as tmpdir:
            binary = Path(tmpdir) / "macos-ocr"
            binary.write_bytes(b"helper")
            ensure_helper.return_value = binary
            run.return_value = subprocess.CompletedProcess(
                args=[str(binary), "/tmp/capture.png"],
                returncode=0,
                stdout='{"text":"项目方向","confidence":0.8,"bbox":{"x":0,"y":0,"width":0.2,"height":0.1},"source":"vision"}\n',
                stderr="",
            )

            result = ocr_image("/tmp/capture.png")

        self.assertIsInstance(result, str)
        self.assertEqual("项目方向", result)
        self.assertEqual(0.8, result.observations[0].confidence)

    @patch("wsa.ocr.platform.system", return_value="Darwin")
    @patch("wsa.ocr.ensure_frontmost_window_helper")
    @patch("wsa.ocr.subprocess.run")
    def test_frontmost_window_id_requires_a_positive_integer(self, run, ensure_helper, system):
        ensure_helper.return_value = "/tmp/frontmost-window"
        run.return_value = subprocess.CompletedProcess(
            args=["/tmp/frontmost-window"],
            returncode=0,
            stdout="4242\n",
            stderr="",
        )

        self.assertEqual(4242, frontmost_window_id())

    @patch("wsa.ocr.platform.system", return_value="Darwin")
    @patch("wsa.ocr.frontmost_window_id", return_value=4242)
    @patch("wsa.ocr.resolve_crop_region", return_value=None)
    @patch("wsa.ocr.subprocess.run")
    def test_window_capture_targets_only_the_frontmost_window(self, run, resolve_crop, window_id, system):
        run.return_value = subprocess.CompletedProcess(
            args=["screencapture"],
            returncode=0,
            stdout="",
            stderr="",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = capture_screenshot(Path(tmpdir) / "capture.png", mode="window")

        self.assertTrue(path.name == "capture.png")
        self.assertEqual(
            ["screencapture", "-x", "-o", "-l", "4242", str(path)],
            run.call_args.args[0],
        )

    @patch("wsa.ocr.ensure_frontmost_helper")
    @patch("wsa.ocr.subprocess.run")
    def test_frontmost_app_status_uses_swift_helper(self, run, ensure_helper):
        ensure_helper.return_value = "/tmp/frontmost"
        run.return_value = subprocess.CompletedProcess(
            args=["/tmp/frontmost"],
            returncode=0,
            stdout="WeChat\n",
            stderr="",
        )

        status = frontmost_app_status()

        self.assertEqual(FrontmostAppStatus(name="WeChat", method="swift", detail="ok"), status)

    @patch("wsa.ocr.ensure_frontmost_helper")
    @patch("wsa.ocr.subprocess.run")
    def test_frontmost_app_status_falls_back_to_osascript(self, run, ensure_helper):
        ensure_helper.side_effect = RuntimeError("compile failed")
        run.return_value = subprocess.CompletedProcess(
            args=["osascript"],
            returncode=0,
            stdout="微信\n",
            stderr="",
        )

        status = frontmost_app_status()

        self.assertEqual("微信", status.name)
        self.assertEqual("osascript", status.method)

    @patch("wsa.ocr.platform.system", return_value="Linux")
    @patch("wsa.ocr.subprocess.run", side_effect=FileNotFoundError("osascript"))
    def test_frontmost_app_status_reports_unavailable_without_osascript(self, run, system):
        status = frontmost_app_status()

        self.assertIsNone(status.name)
        self.assertEqual("swift+osascript", status.method)
        self.assertIn("not macOS", status.detail)
        self.assertIn("osascript unavailable", status.detail)

    @patch("wsa.ocr.frontmost_app_status")
    def test_frontmost_app_name_returns_only_name(self, status):
        status.return_value = FrontmostAppStatus(name="Codex", method="swift", detail="ok")

        self.assertEqual("Codex", frontmost_app_name())

    @patch("wsa.ocr.datetime")
    def test_next_capture_path_uses_subsecond_precision(self, clock):
        local_tz = datetime.now().astimezone().tzinfo
        clock.now.side_effect = [
            datetime(2026, 5, 27, 12, 0, 0, 1000, tzinfo=local_tz),
            datetime(2026, 5, 27, 12, 0, 0, 2000, tzinfo=local_tz),
        ]

        first = next_capture_path(Path("/tmp/wsa"))
        second = next_capture_path(Path("/tmp/wsa"))

        self.assertNotEqual(first, second)
        self.assertEqual("wechat-20260527-120000-001000.png", first.name)
        self.assertEqual("wechat-20260527-120000-002000.png", second.name)

    def test_parse_crop_spec_accepts_x_y_width_height(self):
        self.assertEqual(CropRegion(x=540, y=70, width=2460, height=1770), parse_crop_spec("540,70,2460,1770"))

    @patch("wsa.ocr.image_size")
    def test_resolve_wechat_chat_crop_preset(self, image_size):
        image_size.return_value = (3024, 1964)

        region = resolve_crop_region(Path("/tmp/example.png"), crop_preset="wechat-chat")

        self.assertEqual(CropRegion(x=540, y=70, width=2460, height=1770), region)


if __name__ == "__main__":
    unittest.main()
