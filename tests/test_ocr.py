from pathlib import Path
import subprocess
import unittest
from datetime import datetime
from unittest.mock import patch

from wsa.ocr import (
    CropRegion,
    FrontmostAppStatus,
    frontmost_app_name,
    frontmost_app_status,
    next_capture_path,
    parse_crop_spec,
    resolve_crop_region,
)


class FrontmostAppTests(unittest.TestCase):
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
