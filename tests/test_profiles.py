import tempfile
import unittest
from pathlib import Path

from wsa.profiles import (
    build_profiles,
    ContactProfile,
    extract_files,
    extract_links,
    extract_organizations,
    extract_speakers,
    important_content_lines,
    is_group_chat_name,
    meaningful_content_lines,
    merge_wrapped_lines,
    render_profiles_markdown,
)
from wsa.store import ingest_capture, init_db


class ProfileExtractionTests(unittest.TestCase):
    def test_meaningful_content_lines_skip_ocr_chrome_and_keep_messages(self):
        lines = [
            "目~6.",
            "群成员A",
            "可以参考一下这家",
            "https://example.com/product",
            "昨天 20:30",
            "45.0K",
            "P微信电脑版",
            "同意，先做起来。名称里要有龙虾，以便搜索。",
            "Logseq",
        ]

        self.assertEqual(
            [
                "可以参考一下这家",
                "https://example.com/product",
                "同意，先做起来。名称里要有龙虾，以便搜索。",
            ],
            meaningful_content_lines(lines, chat_name="项目交流群（3）"),
        )

    def test_merge_wrapped_lines_joins_ocr_continuation_lines(self):
        lines = [
            "你看，我能做些什么。喜欢尝试新鲜事物，就当体验了。因为没有迈出第一步，也不知道未来是什",
            "么。",
            "我是怎么把 OpenClaw 和",
            "Hermes 用成一支 AI 团队的",
        ]

        self.assertEqual(
            [
                "你看，我能做些什么。喜欢尝试新鲜事物，就当体验了。因为没有迈出第一步，也不知道未来是什么。",
                "我是怎么把 OpenClaw 和 Hermes 用成一支 AI 团队的",
            ],
            merge_wrapped_lines(lines),
        )

    def test_meaningful_content_lines_merge_after_filtering_speakers(self):
        lines = [
            "群成员A",
            "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。或者咱们打算往哪个方向做，我再",
            "着重研究一下。",
        ]

        self.assertEqual(
            [
                "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。或者咱们打算往哪个方向做，我再着重研究一下。",
            ],
            meaningful_content_lines(lines, chat_name="项目交流群（3）"),
        )

    def test_meaningful_content_lines_keeps_short_ocr_tail_before_timestamp(self):
        lines = [
            "你看，我能做些什么。喜欢尝试新鲜事物，就当体验了。因为没有迈出第一步，也不知道未来是什",
            "么。",
            "5月12日 13:48",
            "好呀，你先去我公众号里看看哈秀念能",
        ]

        self.assertEqual(
            [
                "你看，我能做些什么。喜欢尝试新鲜事物，就当体验了。因为没有迈出第一步，也不知道未来是什么。",
                "好呀，你先去我公众号里看看哈秀念能",
            ],
            meaningful_content_lines(lines, chat_name="联系人B"),
        )

    def test_merge_wrapped_lines_stops_after_ascii_sentence_period(self):
        lines = [
            "我把 OpenClaw 和",
            "Hermes 当成一套 AI 工",
            "作系统来用：多 Agen.",
            "All-in-智能体",
        ]

        self.assertEqual(
            [
                "我把 OpenClaw 和 Hermes 当成一套 AI 工作系统来用：多 Agen.",
                "All-in-智能体",
            ],
            merge_wrapped_lines(lines),
        )

    def test_extract_speakers_links_and_files_from_group_capture(self):
        lines = [
            "群成员A",
            "可以参考一下这家",
            "群成员A",
            "https://example.com/product",
            "群成员A",
            "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。",
            "示例材料.docx",
            "45.0K",
        ]

        self.assertTrue(is_group_chat_name("项目交流群（3）"))
        self.assertEqual(["群成员A"], extract_speakers(lines, chat_name="项目交流群（3）"))
        self.assertEqual(["https://example.com/product"], extract_links(lines))
        self.assertEqual(["示例材料.docx"], extract_files(lines))

    def test_important_content_lines_prioritize_actions_over_system_alerts(self):
        lines = [
            "【月之暗面】尊敬的Moonshot开放平台用户，您",
            "账户已不足¥20.0，请您关注帐户状态，避免",
            "影响业务使用，感谢！",
            "怎么才能得到政策支持",
            "这个是哪里来的？",
            "智能客服本周推出还有哪些工作？我还需要提供哪些？",
        ]

        important = important_content_lines(lines, chat_name="王志平", limit=3)

        self.assertEqual(
            [
                "智能客服本周推出还有哪些工作？我还需要提供哪些？",
                "怎么才能得到政策支持",
                "这个是哪里来的？",
            ],
            important,
        )

    def test_important_content_lines_separate_standalone_links_and_files(self):
        lines = [
            "可以参考一下这家",
            "https://example.com/product",
            "这两个做的挺好，咱们快速学习，跟上",
            "示例材料.docx",
        ]

        important = important_content_lines(lines, chat_name="项目交流群（3）", limit=8)

        self.assertEqual(
            [
                "这两个做的挺好，咱们快速学习，跟上",
                "可以参考一下这家",
            ],
            important,
        )

    def test_important_content_lines_excludes_artifact_only_lines_from_recent_content(self):
        lines = [
            "https://example.com/report",
            "方案.pdf",
            "2.1M",
        ]

        self.assertEqual([], important_content_lines(lines, chat_name="李四", limit=8))

    def test_build_profiles_keeps_artifact_only_capture_out_of_recent_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "李四\n"
                    "https://example.com/report\n"
                    "方案.pdf\n"
                    "2.1M"
                ),
                contact_hint="李四",
                source="test",
                captured_at="2026-05-27T09:00:00+08:00",
            )

            profile = next(item for item in build_profiles(db_path) if item.name == "李四")
            markdown = render_profiles_markdown([profile], title="联系人档案")

        self.assertEqual(("https://example.com/report",), profile.links)
        self.assertEqual(("方案.pdf",), profile.files)
        self.assertEqual((), profile.recent_contents)
        self.assertIn("最近联系内容：\n- 暂无最近联系内容。", markdown)

    def test_meaningful_content_lines_filter_symbol_prefixed_ocr_garbage(self):
        lines = [
            "陈明好，幸会公",
            "我是陈明DANIEL 示例资本。幸会！",
            "德国资本",
            "陈明",
            "§V德国簽本",
            "Daniel Chen 2coe",
        ]

        content = meaningful_content_lines(lines, chat_name="陈明 DANIEL")

        self.assertIn("我是陈明DANIEL 示例资本。幸会！", content)
        self.assertIn("Daniel Chen 2coe", content)
        self.assertNotIn("§V德国簽本", content)

    def test_extract_organizations_uses_context_and_ignores_standalone_ocr_guess(self):
        lines = [
            "我是陈明DANIEL 示例资本。幸会！",
            "德国资本",
            "Daniel Chen 2coe",
            "W 北大国发院",
        ]

        self.assertEqual(["示例资本"], extract_organizations(lines))

    def test_build_profiles_creates_chat_and_group_speaker_profiles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目交流群（3）\n"
                    "群成员A\n"
                    "可以参考一下这家\n"
                    "群成员A\n"
                    "https://example.com/product\n"
                    "17:09\n"
                    "群成员A\n"
                    "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。\n"
                    "示例材料.docx\n"
                    "45.0K\n"
                    "同意，先做起来。名称里要有龙虾，以便搜索。"
                ),
                contact_hint="项目交流群（3）",
                source="test",
                captured_at="2026-05-26T20:41:58+08:00",
            )

            profiles = build_profiles(db_path)

        names = [profile.name for profile in profiles]
        self.assertIn("项目交流群（3）", names)
        self.assertIn("群成员A", names)

        group = next(profile for profile in profiles if profile.name == "项目交流群（3）")
        self.assertEqual("group", group.kind)
        self.assertEqual(("群成员A",), group.speakers)
        self.assertIn("可以参考一下这家", group.recent_contents)
        self.assertIn("示例材料.docx", group.files)
        self.assertEqual((), group.organizations)

        speaker = next(profile for profile in profiles if profile.name == "群成员A")
        self.assertEqual("speaker", speaker.kind)
        self.assertEqual(("项目交流群（3）",), speaker.source_chats)
        self.assertIn("王总，姜总，简单整理了一些我的想法，可以看看是否用得上。", speaker.recent_contents)
        self.assertNotIn("https://example.com/product", speaker.recent_contents)
        self.assertNotIn("示例材料.docx", speaker.recent_contents)

    def test_build_profiles_attributes_group_artifacts_to_the_speaker_who_shared_them(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目群（2）\n"
                    "群成员A\n"
                    "可以参考这个\n"
                    "https://sunny.example/a\n"
                    "Alice\n"
                    "我整理了资料\n"
                    "方案.pdf\n"
                    "2.1M\n"
                    "群成员A\n"
                    "这个方向可行"
                ),
                contact_hint="项目群（2）",
                source="test",
                captured_at="2026-05-27T09:00:00+08:00",
            )

            profiles = build_profiles(db_path)

        group = next(profile for profile in profiles if profile.name == "项目群（2）")
        sunny = next(profile for profile in profiles if profile.name == "群成员A")
        alice = next(profile for profile in profiles if profile.name == "Alice")

        self.assertEqual(("Alice", "群成员A"), group.speakers)
        self.assertEqual(("https://sunny.example/a",), group.links)
        self.assertEqual(("方案.pdf",), group.files)
        self.assertEqual(("https://sunny.example/a",), sunny.links)
        self.assertEqual((), sunny.files)
        self.assertEqual((), alice.links)
        self.assertEqual(("方案.pdf",), alice.files)

    def test_build_profiles_does_not_attribute_messages_after_timestamp_to_previous_speaker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目群（2）\n"
                    "群成员A\n"
                    "可以参考一下这家\n"
                    "昨天 20:30\n"
                    "这两个做的挺好，咱们快速学习，跟上\n"
                    "17:09\n"
                    "群成员A\n"
                    "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。"
                ),
                contact_hint="项目群（2）",
                source="test",
                captured_at="2026-05-27T09:00:00+08:00",
            )

            profiles = build_profiles(db_path)

        group = next(profile for profile in profiles if profile.name == "项目群（2）")
        sunny = next(profile for profile in profiles if profile.name == "群成员A")

        self.assertIn("这两个做的挺好，咱们快速学习，跟上", group.recent_contents)
        self.assertIn("可以参考一下这家", sunny.recent_contents)
        self.assertIn("王总，姜总，简单整理了一些我的想法，可以看看是否用得上。", sunny.recent_contents)
        self.assertNotIn("这两个做的挺好，咱们快速学习，跟上", sunny.recent_contents)

    def test_build_profiles_does_not_attribute_links_after_timestamp_to_previous_speaker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目群（2）\n"
                    "群成员A\n"
                    "可以参考这个\n"
                    "昨天 20:30\n"
                    "https://mine.example/outgoing\n"
                    "17:09\n"
                    "Alice\n"
                    "我整理了资料\n"
                    "方案.pdf"
                ),
                contact_hint="项目群（2）",
                source="test",
                captured_at="2026-05-27T09:00:00+08:00",
            )

            profiles = build_profiles(db_path)

        group = next(profile for profile in profiles if profile.name == "项目群（2）")
        sunny = next(profile for profile in profiles if profile.name == "群成员A")
        alice = next(profile for profile in profiles if profile.name == "Alice")

        self.assertEqual(("https://mine.example/outgoing",), group.links)
        self.assertEqual((), sunny.links)
        self.assertEqual(("方案.pdf",), alice.files)

    def test_build_profiles_attributes_group_signals_to_the_speaker_who_triggered_them(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目群（2）\n"
                    "群成员A\n"
                    "可以参考这个方案\n"
                    "Alice\n"
                    "这个项目怎么推进？需要哪些资源？"
                ),
                contact_hint="项目群（2）",
                source="test",
                captured_at="2026-05-27T09:00:00+08:00",
            )

            profiles = build_profiles(db_path)

        group = next(profile for profile in profiles if profile.name == "项目群（2）")
        sunny = next(profile for profile in profiles if profile.name == "群成员A")
        alice = next(profile for profile in profiles if profile.name == "Alice")

        self.assertEqual(("project", "question"), group.signals)
        self.assertEqual((), sunny.signals)
        self.assertEqual(("project", "question"), alice.signals)

    def test_build_profiles_attributes_group_organizations_to_the_speaker_who_mentioned_them(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "项目群（2）\n"
                    "Alice\n"
                    "我是 Alice，来自蓝海资本。\n"
                    "群成员A\n"
                    "这个项目怎么推进？需要哪些资源？"
                ),
                contact_hint="项目群（2）",
                source="test",
                captured_at="2026-05-27T09:00:00+08:00",
            )

            profiles = build_profiles(db_path)

        group = next(profile for profile in profiles if profile.name == "项目群（2）")
        alice = next(profile for profile in profiles if profile.name == "Alice")
        sunny = next(profile for profile in profiles if profile.name == "群成员A")

        self.assertEqual(("蓝海资本",), group.organizations)
        self.assertEqual(("蓝海资本",), alice.organizations)
        self.assertEqual((), sunny.organizations)

    def test_render_profiles_markdown_contains_contact_centered_sections(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="王志平\n智能客服本周推出还有哪些工作？我还需要提供哪些？",
                contact_hint="王志平",
                source="test",
                captured_at="2026-05-26T20:41:47+08:00",
            )

            markdown = render_profiles_markdown(build_profiles(db_path), title="联系人档案")

        self.assertIn("# 联系人档案", markdown)
        self.assertIn("## 王志平", markdown)
        self.assertIn("最近联系内容", markdown)
        self.assertIn("智能客服本周推出还有哪些工作？我还需要提供哪些？", markdown)

    def test_render_profiles_markdown_handles_empty_profiles(self):
        markdown = render_profiles_markdown([], title="联系人档案")

        self.assertEqual("# 联系人档案\n\n暂无联系人档案。\n", markdown)

    def test_render_profiles_markdown_handles_profile_without_recent_content(self):
        markdown = render_profiles_markdown(
            [
                ContactProfile(
                    name="王五",
                    kind="direct",
                    source_chats=(),
                    last_seen_at="2026-05-27T10:00:00+08:00",
                    recent_contents=(),
                    links=("https://example.com",),
                )
            ],
            title="联系人档案",
        )

        self.assertIn("- 最近出现：2026-05-27 10:00", markdown)
        self.assertNotIn("2026-05-27T10:00:00+08:00", markdown)
        self.assertIn("最近联系内容：\n- 暂无最近联系内容。", markdown)

    def test_render_profiles_markdown_uses_chinese_relationship_signal_labels(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="王志平\n智能客服项目本周推出还有哪些工作？我还需要提供哪些？",
                contact_hint="王志平",
                source="test",
                captured_at="2026-05-27T10:00:00+08:00",
            )

            markdown = render_profiles_markdown(build_profiles(db_path), title="联系人档案")

        self.assertIn("- 关系信号：项目/合作, 问题", markdown)
        self.assertNotIn("project", markdown)
        self.assertNotIn("question", markdown)

    def test_render_profiles_markdown_contains_organization_hints(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text="陈明 DANIEL\n我是陈明DANIEL 示例资本。幸会！\n德国资本",
                contact_hint="陈明 DANIEL",
                source="test",
                captured_at="2026-05-26T20:41:47+08:00",
            )

            markdown = render_profiles_markdown(build_profiles(db_path), title="联系人档案")

        self.assertIn("- 机构/公司：示例资本", markdown)
        self.assertNotIn("- 机构/公司：德国资本", markdown)
        self.assertNotIn("北大国发院", markdown)

    def test_build_profiles_removes_standalone_organization_ocr_fragments_from_recent_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "陈明 DANIEL\n"
                    "我是陈明DANIEL 示例资本。幸会！\n"
                    "德国资本\n"
                    "陈明"
                ),
                contact_hint="陈明 DANIEL",
                source="test",
                captured_at="2026-05-26T20:41:47+08:00",
            )

            profiles = build_profiles(db_path)

        profile = next(item for item in profiles if item.name == "陈明 DANIEL")
        self.assertEqual(("示例资本",), profile.organizations)
        self.assertIn("我是陈明DANIEL 示例资本。幸会！", profile.recent_contents)
        self.assertNotIn("德国资本", profile.recent_contents)

    def test_build_profiles_moves_standalone_card_name_fragments_to_identity_hints(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "陈明 DANIEL\n"
                    "我是陈明DANIEL 示例资本。幸会！\n"
                    "陈明\n"
                    "Daniel Chen 2coe"
                ),
                contact_hint="陈明 DANIEL",
                source="test",
                captured_at="2026-05-26T20:41:47+08:00",
            )

            profile = next(item for item in build_profiles(db_path) if item.name == "陈明 DANIEL")
            markdown = render_profiles_markdown([profile], title="联系人档案")

        self.assertEqual(("陈明", "Daniel Chen"), getattr(profile, "identity_hints", ()))
        self.assertIn("- 身份线索：陈明, Daniel Chen", markdown)
        self.assertIn("我是陈明DANIEL 示例资本。幸会！", profile.recent_contents)
        self.assertNotIn("陈明", profile.recent_contents)
        self.assertNotIn("Daniel Chen 2coe", profile.recent_contents)

    def test_build_profiles_does_not_treat_article_titles_as_identity_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "social.db"
            init_db(db_path)
            ingest_capture(
                db_path,
                raw_text=(
                    "联系人B\n"
                    "我是怎么把 OpenClaw 和\n"
                    "Hermes 用成一支 AI 团队的\n"
                    "◎ 直播中\n"
                    "日 蒸集盟\n"
                    "围蘇州\n"
                    "“十五五”开局之年的宏观经济挑战与金融转型"
                ),
                contact_hint="联系人B",
                source="test",
                captured_at="2026-05-26T20:41:47+08:00",
            )

            profile = next(item for item in build_profiles(db_path) if item.name == "联系人B")
            markdown = render_profiles_markdown([profile], title="联系人档案")

        self.assertEqual((), getattr(profile, "identity_hints", ()))
        self.assertNotIn("身份线索", markdown)
        self.assertNotIn("围蘇州", profile.recent_contents)


if __name__ == "__main__":
    unittest.main()
