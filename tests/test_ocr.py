from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from wsa.ocr import (
    CropRegion,
    FrontmostAppStatus,
    frontmost_app_name,
    frontmost_app_status,
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

    @patch("wsa.ocr.frontmost_app_status")
    def test_frontmost_app_name_returns_only_name(self, status):
        status.return_value = FrontmostAppStatus(name="Codex", method="swift", detail="ok")

        self.assertEqual("Codex", frontmost_app_name())

    def test_parse_crop_spec_accepts_x_y_width_height(self):
        self.assertEqual(CropRegion(x=540, y=70, width=2460, height=1770), parse_crop_spec("540,70,2460,1770"))

    @patch("wsa.ocr.image_size")
    def test_resolve_wechat_chat_crop_preset(self, image_size):
        image_size.return_value = (3024, 1964)

        region = resolve_crop_region(Path("/tmp/example.png"), crop_preset="wechat-chat")

        self.assertEqual(CropRegion(x=540, y=70, width=2460, height=1770), region)


if __name__ == "__main__":
    unittest.main()
