from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import socket
import threading
import unittest
from urllib.request import urlopen

from wsa.observations import OCRObservation
from wsa.store import ingest_capture, init_db
from wsa.web import (
    INDEX_HTML,
    DashboardHandler,
    DashboardHTTPServer,
    build_overview,
    capture_detail,
    list_captures,
    serve_dashboard,
)


def _loopback_bind_available() -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
        return True
    except OSError:
        return False


class WebDashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "data" / "social.db"
        self.captures = self.root / "data" / "captures"
        self.captures.mkdir(parents=True)
        init_db(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_overview_and_capture_detail_are_read_only_and_structured(self):
        image = self.captures / "wechat-test.png"
        image.write_bytes(b"not-a-real-png-but-a-managed-test-image")
        result = ingest_capture(
            self.db,
            raw_text="张三\n你好，最近怎么样？",
            contact_hint="张三",
            source="manual",
            image_path=str(image),
            captured_at="2026-08-24T09:00:00+08:00",
            observations=[
                OCRObservation(text="张三", confidence=0.92, source="vision"),
                OCRObservation(text="你好，最近怎么样？", confidence=0.42, source="vision"),
            ],
        )
        before = self.db.stat().st_mtime_ns
        overview = build_overview(self.db, captures_dir=self.captures, include_connectors=False)
        after = self.db.stat().st_mtime_ns

        self.assertEqual(before, after)
        self.assertTrue(overview["db"]["exists"])
        self.assertEqual(1, overview["counts"]["captures"])
        self.assertEqual(2, overview["counts"]["observations"])
        self.assertEqual(1, overview["counts"]["pending_low_confidence"])
        self.assertEqual(0.67, overview["quality"]["average_confidence"])
        self.assertEqual(1, overview["screenshots"]["count"])
        self.assertTrue(overview["latest"]["image_available"])

        captures = list_captures(self.db, captures_dir=self.captures)
        self.assertEqual([result.capture_id], [item["id"] for item in captures])
        self.assertEqual(1, captures[0]["low_confidence_count"])
        self.assertEqual("manual", captures[0]["source"])

        detail = capture_detail(self.db, result.capture_id, captures_dir=self.captures)
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertTrue(detail["image_available"])
        self.assertEqual("vision", detail["observations"][0]["source"])
        self.assertEqual("pending", detail["observations"][1]["review_status"])

    def test_missing_db_and_unmanaged_image_do_not_leak_files(self):
        missing = self.root / "missing.db"
        overview = build_overview(missing, captures_dir=self.captures, include_connectors=False)
        self.assertFalse(overview["db"]["exists"])
        self.assertEqual([], list_captures(missing, captures_dir=self.captures))
        self.assertIsNone(capture_detail(missing, 1, captures_dir=self.captures))

        outside = self.root / "outside.png"
        outside.write_bytes(b"outside")
        result = ingest_capture(
            self.db,
            raw_text="外部图片证据",
            contact_hint="外部联系人",
            source="image",
            image_path=str(outside),
        )
        detail = capture_detail(self.db, result.capture_id, captures_dir=self.captures)
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertFalse(detail["image_available"])

    def test_crm_view_summarizes_contacts_and_filters_noise(self):
        from wsa.web import build_crm_view

        ingest_capture(
            self.db,
            raw_text="王志平\n我通过了你的朋友验证请求，现在我们可以开始聊天了\n下周三线下分享见",
            contact_hint="王志平",
            source="manual",
            captured_at="2026-08-20T09:00:00+08:00",
        )
        view = build_crm_view(self.db, captures_dir=self.captures)

        self.assertEqual("crm", view["mode"])
        names = [contact["name"] for contact in view["contacts"]]
        self.assertIn("王志平", names)
        # Filler phrases and UI labels must never become CRM contacts.
        for noise in ("收到", "好的", "取消", "转发"):
            self.assertNotIn(noise, names)
        self.assertEqual(view["stats"]["contacts"], len(names))
        contact = view["contacts"][names.index("王志平")]
        self.assertEqual("直接联系人", contact["kind_label"])
        self.assertEqual(1, contact["interaction_count"])
        event = contact["timeline"][0]
        self.assertEqual("2026-08-20T09:00:00+08:00", event["captured_at"])
        self.assertIn("下周三线下分享见", event["summary"])

    def test_crm_view_explains_when_only_session_list_was_captured(self):
        from wsa.web import build_crm_view

        ingest_capture(
            self.db,
            raw_text="微信会话列表\n项目群 有 3 条新消息\n服务通知",
            contact_hint="微信会话列表",
            source="watch",
            captured_at="2026-08-24T09:00:00+08:00",
        )
        view = build_crm_view(self.db, captures_dir=self.captures)

        self.assertEqual([], view["contacts"])
        self.assertEqual(1, view["stats"]["captures"])
        self.assertTrue(view["notices"])
        self.assertIn("打开具体联系人聊天窗口", view["notices"][0]["message"])

    def test_contact_meta_save_merges_and_roundtrips_to_crm_view(self):
        from wsa.enrichment import record_contact_enrichment
        from wsa.web import build_crm_view, save_contact_meta

        ingest_capture(
            self.db,
            raw_text="王志平\n下周三线下分享见",
            contact_hint="王志平",
            source="manual",
            captured_at="2026-08-20T09:00:00+08:00",
        )
        record_contact_enrichment(self.db, person_name="王志平", fields={"company": "得到"}, source="obsidian")

        result = save_contact_meta(
            self.db,
            person_name="王志平",
            updates={"category": "同事", "tags": "AI, 读书", "notes": "周三分享"},
        )
        self.assertTrue(result["saved"])
        # Merging must preserve fields from other sources.
        self.assertEqual("得到", result["fields"]["company"])
        self.assertEqual("同事", result["fields"]["category"])

        view = build_crm_view(self.db, captures_dir=self.captures)
        contact = next(item for item in view["contacts"] if item["name"] == "王志平")
        self.assertEqual("同事", contact["category"])
        self.assertEqual("AI, 读书", contact["tags"])
        self.assertEqual("周三分享", contact["notes"])

        cleared = save_contact_meta(
            self.db, person_name="王志平", updates={"category": "", "tags": "", "notes": ""}
        )
        self.assertTrue(cleared["saved"])
        self.assertNotIn("category", cleared["fields"])
        self.assertEqual("得到", cleared["fields"]["company"])

        with self.assertRaises(ValueError):
            save_contact_meta(self.db, person_name="  ", updates={"category": "朋友"})

    def test_crm_view_only_shows_group_speakers_already_in_contacts(self):
        from wsa.web import build_crm_view

        # 王志平 is known (direct chat captured); 路人甲 only ever spoke in a group.
        ingest_capture(
            self.db,
            raw_text="王志平\n你好",
            contact_hint="王志平",
            source="manual",
            captured_at="2026-08-20T09:00:00+08:00",
        )
        ingest_capture(
            self.db,
            raw_text=(
                "项目交流群（3）\n"
                "王志平\n下周三线下分享见\n"
                "路人甲\n这个方案我研究一下再回复你"
            ),
            contact_hint="项目交流群（3）",
            source="manual",
            captured_at="2026-08-21T09:00:00+08:00",
        )
        view = build_crm_view(self.db, captures_dir=self.captures)
        names = [contact["name"] for contact in view["contacts"]]

        self.assertIn("王志平", names)
        self.assertNotIn("路人甲", names)

    def test_ui_only_binds_to_loopback(self):
        with self.assertRaises(ValueError):
            serve_dashboard(self.db, host="0.0.0.0", port=8788, open_browser=False)

    def test_embedded_page_has_read_only_crm_views(self):
        self.assertIn("关系面板", INDEX_HTML)
        self.assertIn("/api/crm", INDEX_HTML)
        self.assertIn("contactSearch", INDEX_HTML)
        self.assertIn("谈话时间线", INDEX_HTML)
        self.assertIn("来自群聊", INDEX_HTML)
        self.assertIn("只读", INDEX_HTML)

    @unittest.skipUnless(_loopback_bind_available(), "sandbox does not allow loopback socket binding")
    def test_http_routes_serve_dashboard_and_managed_image(self):
        image = self.captures / "route-test.png"
        image.write_bytes(b"route-image")
        result = ingest_capture(
            self.db,
            raw_text="路由检查",
            contact_hint="路由联系人",
            source="manual",
            image_path=str(image),
        )
        server = DashboardHTTPServer(
            ("127.0.0.1", 0),
            DashboardHandler,
            db_path=self.db,
            captures_dir=self.captures,
            log_file=self.root / "data" / "watch.log",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/", timeout=2) as response:
                self.assertIn("text/html", response.headers["Content-Type"])
                self.assertIn("关系面板", response.read().decode("utf-8"))
            with urlopen(base + "/api/overview", timeout=2) as response:
                self.assertEqual(1, json.loads(response.read())["counts"]["captures"])
            with urlopen(base + f"/api/captures/{result.capture_id}", timeout=2) as response:
                self.assertEqual(result.capture_id, json.loads(response.read())["id"])
            with urlopen(base + f"/media/{result.capture_id}", timeout=2) as response:
                self.assertEqual(b"route-image", response.read())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


    @unittest.skipUnless(_loopback_bind_available(), "sandbox does not allow loopback socket binding")
    def test_http_post_enrichment_edits_contact_meta(self):
        from urllib.error import HTTPError
        from urllib.request import Request

        ingest_capture(self.db, raw_text="王志平\n下周三见", contact_hint="王志平", source="manual")
        server = DashboardHTTPServer(
            ("127.0.0.1", 0),
            DashboardHandler,
            db_path=self.db,
            captures_dir=self.captures,
            log_file=self.root / "data" / "watch.log",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            body = json.dumps(
                {"person_name": "王志平", "category": "朋友", "tags": "读书", "notes": "线下活动认识"}
            ).encode("utf-8")
            request = Request(base + "/api/enrichment", data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=2) as response:
                payload = json.loads(response.read())
            self.assertTrue(payload["saved"])
            self.assertEqual("朋友", payload["fields"]["category"])

            with urlopen(base + "/api/crm", timeout=2) as response:
                crm = json.loads(response.read())
            contact = next(item for item in crm["contacts"] if item["name"] == "王志平")
            self.assertEqual("读书", contact["tags"])
            self.assertEqual("线下活动认识", contact["notes"])

            with self.assertRaises(HTTPError) as ctx:
                urlopen(Request(base + "/api/nope", data=body, method="POST"), timeout=2)
            self.assertEqual(404, ctx.exception.code)
            with self.assertRaises(HTTPError) as ctx:
                urlopen(Request(base + "/api/enrichment", data=b"not-json", method="POST"), timeout=2)
            self.assertEqual(400, ctx.exception.code)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    @unittest.skipUnless(_loopback_bind_available(), "sandbox does not allow loopback socket binding")
    def test_http_outreach_routes_list_and_update_drafts(self):
        from urllib.request import Request

        from wsa.outreach import CREATE_CONFIRMATION_TEXT, create_outreach_drafts

        created = create_outreach_drafts(
            self.db,
            items=[{"person_name": "王志平", "draft_text": "Kiwi 新版上线了。"}],
            campaign="kiwi-release",
            confirmed=True,
            confirmation_text=CREATE_CONFIRMATION_TEXT,
        )
        server = DashboardHTTPServer(
            ("127.0.0.1", 0),
            DashboardHandler,
            db_path=self.db,
            captures_dir=self.captures,
            log_file=self.root / "data" / "watch.log",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/api/outreach?status=draft", timeout=2) as response:
                drafts = json.loads(response.read())["drafts"]
            self.assertEqual([created[0].id], [draft["id"] for draft in drafts])

            body = json.dumps({"draft_id": created[0].id, "action": "approve"}).encode("utf-8")
            request = Request(base + "/api/outreach", data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=2) as response:
                payload = json.loads(response.read())
            self.assertEqual("approved", payload["draft"]["status"])

            with urlopen(base + "/api/outreach?status=approved", timeout=2) as response:
                approved = json.loads(response.read())["drafts"]
            self.assertEqual([created[0].id], [draft["id"] for draft in approved])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
