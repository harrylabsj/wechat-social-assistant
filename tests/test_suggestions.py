import sqlite3
import tempfile
import unittest
from pathlib import Path

from wsa.suggestions import build_suggestions, render_markdown
from wsa.store import ingest_capture, init_db


class SuggestionTests(unittest.TestCase):
    def test_build_suggestions_prioritizes_unanswered_and_project_followup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="赵六\n上次的问题你还没回复我，方便的时候看下。",
                contact_hint="赵六",
                source="test",
                captured_at="2026-05-25T09:00:00+08:00",
            )
            ingest_capture(
                db_path,
                raw_text="钱七\n最近项目推进得还行，下个月可能需要找人聊聊。",
                contact_hint="钱七",
                source="test",
                captured_at="2026-05-10T09:00:00+08:00",
            )

            suggestions = build_suggestions(db_path, as_of="2026-05-26T10:00:00+08:00")

        self.assertEqual(["赵六", "钱七"], [item.person_name for item in suggestions])
        self.assertEqual("补回复", suggestions[0].action)
        self.assertIn("还没回复", suggestions[0].why)
        self.assertIn("项目", suggestions[1].draft)

    def test_render_markdown_contains_action_table_and_drafts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="孙八\n下周约饭吗？",
                contact_hint="孙八",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
            )

            markdown = render_markdown(
                build_suggestions(db_path, as_of="2026-05-26T10:00:00+08:00"),
                title="今日社交跟进",
            )

        self.assertIn("# 今日社交跟进", markdown)
        self.assertIn("| 人 | 分数 | 强度 | 最近互动 | 建议动作 | 原因 | 微信草稿 |", markdown)
        self.assertIn("| 孙八 | 65 | 中（有明确关系信号，适合跟进） | 2026-05-26 09:00 | 确认时间 |", markdown)
        self.assertNotIn("2026-05-26T09:00:00+08:00", markdown)
        self.assertIn("微信草稿", markdown)

    def test_render_markdown_handles_empty_suggestions(self):
        markdown = render_markdown([], title="今日社交跟进")

        self.assertIn("# 今日社交跟进", markdown)
        self.assertIn("暂无需要跟进的联系人。", markdown)
        self.assertNotIn("| 人 | 分数 | 强度 |", markdown)

    def test_build_suggestions_skips_ui_noise_people(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="微信 文件 编辑\n显示\n窗口\n帮助\n项目",
                contact_hint="微信 文件 编辑",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
            )
            ingest_capture(
                db_path,
                raw_text="陈明 DANIEL\n我是陆陈明 DANIEL 示例资本。幸会！",
                contact_hint="陈明 DANIEL",
                source="test",
                captured_at="2026-05-26T09:01:00+08:00",
            )

            suggestions = build_suggestions(db_path, as_of="2026-05-26T10:00:00+08:00")

        self.assertEqual(["陈明 DANIEL"], [item.person_name for item in suggestions])

    def test_build_suggestions_min_score_filters_recent_low_priority_contacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="李四\n最近看到一篇文章，挺有意思。",
                contact_hint="李四",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
            )
            ingest_capture(
                db_path,
                raw_text="孙八\n下周约饭吗？",
                contact_hint="孙八",
                source="test",
                captured_at="2026-05-26T09:01:00+08:00",
            )

            suggestions = build_suggestions(
                db_path,
                as_of="2026-05-26T10:00:00+08:00",
                min_score=45,
            )

        self.assertEqual(["孙八"], [item.person_name for item in suggestions])
        self.assertEqual("确认时间", suggestions[0].action)

    def test_build_suggestions_keeps_recent_strong_signal_when_latest_capture_is_lightweight(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="李四\n下周方便聊聊你那个新项目吗？",
                contact_hint="李四",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
            )
            ingest_capture(
                db_path,
                raw_text="李四\n最近看到一篇文章，挺有意思。",
                contact_hint="李四",
                source="test",
                captured_at="2026-05-26T09:30:00+08:00",
            )

            suggestions = build_suggestions(db_path, as_of="2026-05-26T10:00:00+08:00")

        self.assertEqual(["李四"], [item.person_name for item in suggestions])
        self.assertEqual("确认时间", suggestions[0].action)
        self.assertIn("约时间", suggestions[0].why)
        self.assertIn("新项目", suggestions[0].draft)

    def test_light_greeting_draft_for_shared_article_does_not_ask_about_progress(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="李四\n最近看到一篇文章，挺有意思。",
                contact_hint="李四",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
            )

            suggestions = build_suggestions(db_path, as_of="2026-05-26T10:00:00+08:00")

        draft = suggestions[0].draft
        self.assertIn("那篇文章", draft)
        self.assertIn("值得看的内容", draft)
        self.assertNotIn("最近进展", draft)
        self.assertNotIn("看到你上次说到", draft)

    def test_light_greeting_draft_for_artifact_only_capture_mentions_shared_materials(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="李四\nhttps://example.com/report\n方案.pdf\n2.1M",
                contact_hint="李四",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
            )

            suggestions = build_suggestions(db_path, as_of="2026-05-26T10:00:00+08:00")

        draft = suggestions[0].draft
        self.assertIn("分享的链接和文件", draft)
        self.assertIn("新的内容", draft)
        self.assertNotIn("https://example.com", draft)
        self.assertNotIn("方案.pdf", draft)
        self.assertNotIn("最近进展", draft)
        self.assertNotIn("看到你上次说到这件事", draft)

    def test_draft_topic_skips_timestamp_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="陈明 DANIEL\n18:19\n我是陆陈明 DANIEL 示例资本。幸会！",
                contact_hint="陈明 DANIEL",
                source="test",
                captured_at="2026-05-26T09:01:00+08:00",
            )

            suggestions = build_suggestions(db_path, as_of="2026-05-26T10:00:00+08:00")

        self.assertIn("示例资本", suggestions[0].draft)
        self.assertNotIn("18:19", suggestions[0].draft)

    def test_light_greeting_draft_uses_identity_context_without_quoting_self_intro(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="陈明 DANIEL\n我是陆陈明 DANIEL 示例资本。幸会！\n陈明\nDaniel Chen",
                contact_hint="陈明 DANIEL",
                source="test",
                captured_at="2026-05-26T09:01:00+08:00",
            )

            suggestions = build_suggestions(db_path, as_of="2026-05-26T10:00:00+08:00")

        draft = suggestions[0].draft
        self.assertIn("示例资本", draft)
        self.assertNotIn("看到你上次说到我是", draft)
        self.assertNotIn("上次说到我是陈明", draft)

    def test_light_greeting_draft_for_personal_reflection_does_not_ask_about_progress(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "联系人B\n"
                    "你看，我能做些什么。喜欢尝试新鲜事物，就当体验了。因为没有迈出第一步，也不知道未来是什么。"
                ),
                contact_hint="联系人B",
                source="test",
                captured_at="2026-05-26T09:01:00+08:00",
            )

            suggestions = build_suggestions(db_path, as_of="2026-05-26T10:00:00+08:00")

        draft = suggestions[0].draft
        self.assertIn("上次聊到尝试新鲜事物和迈出第一步这件事", draft)
        self.assertIn("最近还好吗", draft)
        self.assertNotIn("我能做些什么", draft)
        self.assertNotIn("最近进展", draft)
        self.assertNotIn("看到你上次说到", draft)

    def test_draft_topic_skips_short_ocr_garbage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="项目交流群（3）\n目~6.\n群成员A\n可以参考一下这家",
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-26T09:01:00+08:00",
            )

            suggestions = build_suggestions(db_path, as_of="2026-05-26T10:00:00+08:00")

        self.assertIn("可以参考一下这家", suggestions[0].draft)
        self.assertNotIn("目~6", suggestions[0].draft)

    def test_group_chat_draft_uses_group_tone_instead_of_addressing_group_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。或者咱们打算往哪个方向做，我再\n"
                    "着重研究一下。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-26T09:01:00+08:00",
            )

            suggestions = build_suggestions(db_path, as_of="2026-05-26T10:00:00+08:00")

        self.assertIn("群里上次聊到", suggestions[0].draft)
        self.assertNotIn("项目交流群（3），看到你上次说到", suggestions[0].draft)

    def test_build_suggestions_prefers_group_speaker_for_project_followup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "群成员A\n"
                    "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。或者咱们打算往哪个方向做，我再\n"
                    "着重研究一下。\n"
                    "同意，先做起来。名称里要有龙虾，以便搜索。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-26T09:01:00+08:00",
            )

            suggestions = build_suggestions(
                db_path,
                as_of="2026-05-26T10:00:00+08:00",
                min_score=45,
            )

        self.assertEqual(["群成员A"], [item.person_name for item in suggestions])
        self.assertEqual("项目跟进", suggestions[0].action)
        self.assertIn("项目/合作", suggestions[0].why)
        self.assertIn("来自群：项目交流群（3）", suggestions[0].why)
        self.assertIn("群成员A，上次你在「项目交流群（3）」里提到", suggestions[0].draft)
        self.assertIn("简单整理了一些我的想法", suggestions[0].draft)
        self.assertNotIn("提到王总，姜总", suggestions[0].draft)

    def test_build_suggestions_does_not_refresh_stale_speaker_signal_with_latest_light_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "群成员A\n"
                    "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-01T09:00:00+08:00",
            )
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "群成员A\n"
                    "最近看到一篇文章，挺有意思。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-26T09:00:00+08:00",
            )

            suggestions = build_suggestions(
                db_path,
                as_of="2026-05-26T10:00:00+08:00",
                min_score=45,
            )

        self.assertEqual([], suggestions)

    def test_draft_topic_prefers_high_value_question(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "王志平\n"
                    "OPC商业...\n"
                    "怎么才能得到政策支持\n"
                    "智能客服本周推出还有哪些工作？我还需要提供哪些？"
                ),
                contact_hint="王志平",
                source="test",
                captured_at="2026-05-26T09:01:00+08:00",
            )

            suggestions = build_suggestions(db_path, as_of="2026-05-26T10:00:00+08:00")

        self.assertIn("智能客服本周推出还有哪些工作", suggestions[0].draft)
        self.assertNotIn("OPC商业", suggestions[0].draft)

    def test_build_suggestions_recomputes_signals_with_current_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            result = ingest_capture(
                db_path,
                raw_text="联系人B\n我是怎么把 OpenClaw 和\nHermes 用成一支 AI 团队的",
                contact_hint="联系人B",
                source="test",
                captured_at="2026-05-26T09:01:00+08:00",
            )
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "insert or ignore into capture_signals (capture_id, kind, phrase) values (?, ?, ?)",
                    (result.capture_id, "question", "legacy"),
                )

            suggestions = build_suggestions(db_path, as_of="2026-05-26T10:00:00+08:00")

        self.assertEqual("轻量问候", suggestions[0].action)

    def test_draft_topic_uses_merged_wrapped_ocr_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="联系人B\n我是怎么把 OpenClaw 和\nHermes 用成一支 AI 团队的",
                contact_hint="联系人B",
                source="test",
                captured_at="2026-05-26T09:01:00+08:00",
            )

            suggestions = build_suggestions(db_path, as_of="2026-05-26T10:00:00+08:00")

        self.assertIn("OpenClaw 和 Hermes", suggestions[0].draft)
        self.assertNotIn("OpenClaw 和，", suggestions[0].draft)
        self.assertNotIn("这件事", suggestions[0].draft)


if __name__ == "__main__":
    unittest.main()
