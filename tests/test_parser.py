import unittest

from wsa.parser import extract_signals, is_noise_line, normalize_lines, parse_capture


class ParserTests(unittest.TestCase):
    def test_normalize_lines_removes_common_wechat_chrome(self):
        raw = """
        微信 文件 编辑 显示 窗口 帮助
        5月26日 周二 20:16
        Q 搜索
        张三
        昨天 22:01
        我最近在做 AI 客服项目

        发送
        """

        lines = normalize_lines(raw)

        self.assertEqual(lines, ["张三", "昨天 22:01", "我最近在做 AI 客服项目"])

    def test_is_noise_line_catches_macos_and_wechat_status_chrome(self):
        for line in [
            "微信 文件 编辑 显示 窗口帮助",
            "显示 窗口 帮助",
            "Q8∞ 5月26日周二 20:16",
            "Q 搜索",
            "4KB/s 6KB/s",
            "Codex",
            "你已添加了陈明 DANIEL，以上是打招呼的消息。",
        ]:
            self.assertTrue(is_noise_line(line), line)

    def test_parse_capture_uses_hint_and_keeps_clean_transcript(self):
        parsed = parse_capture(
            "搜索\n李四\n下周约饭吗？我想聊聊你那个新项目\n发送",
            contact_hint="李四",
        )

        self.assertEqual(parsed.contact_name, "李四")
        self.assertIn("下周约饭吗？我想聊聊你那个新项目", parsed.clean_text)
        self.assertIn("schedule", parsed.signal_kinds)
        self.assertIn("project", parsed.signal_kinds)

    def test_extract_signals_finds_relationship_followup_cues(self):
        signals = extract_signals("生日快乐！最近项目推进得怎么样？有空约个饭，我还没回复你上次的问题。")
        kinds = {signal.kind for signal in signals}

        self.assertEqual(
            {"birthday", "project", "schedule", "needs_reply", "question"},
            kinds,
        )

    def test_extract_signals_does_not_treat_first_person_unanswered_work_as_needs_reply(self):
        signals = extract_signals("群成员A 这个项目我还没回复，今天需要推进一下。")
        kinds = {signal.kind for signal in signals}

        self.assertNotIn("needs_reply", kinds)
        self.assertIn("project", kinds)

    def test_extract_signals_treats_second_person_context_before_first_person_reply_as_needs_reply(self):
        signals = extract_signals("你上次提到的那个政策支持问题，我这边还没回复，晚点补给你。")
        kinds = {signal.kind for signal in signals}

        self.assertIn("needs_reply", kinds)

    def test_extract_signals_treats_group_planning_as_project_signal(self):
        signals = extract_signals(
            "王总，姜总，简单整理了一些我的想法，可以看看是否用得上。"
            "或者咱们打算往哪个方向做，我再着重研究一下。"
            "同意，先做起来。名称里要有龙虾，以便搜索。"
        )
        kinds = {signal.kind for signal in signals}

        self.assertIn("project", kinds)

    def test_extract_signals_does_not_treat_article_title_as_question(self):
        signals = extract_signals("我是怎么把 OpenClaw 和 Hermes 用成一支 AI 团队的")
        kinds = {signal.kind for signal in signals}

        self.assertNotIn("question", kinds)

    def test_extract_signals_does_not_treat_split_article_title_as_question(self):
        signals = extract_signals("我是怎么把 OpenClaw 和\nHermes 用成一支 AI 团队的")
        kinds = {signal.kind for signal in signals}

        self.assertNotIn("question", kinds)

    def test_extract_signals_does_not_treat_statement_with_something_as_question(self):
        signals = extract_signals("你看，我能做些什么。喜欢尝试新鲜事物。")
        kinds = {signal.kind for signal in signals}

        self.assertNotIn("question", kinds)

    def test_extract_signals_keeps_real_question_without_question_mark(self):
        signals = extract_signals("智能客服本周推出还有哪些工作？我还需要提供哪些？怎么才能得到政策支持")
        kinds = {signal.kind for signal in signals}

        self.assertIn("question", kinds)

    def test_extract_signals_keeps_real_question_with_question_mark(self):
        signals = extract_signals("这个是什么？哪里来的？")
        kinds = {signal.kind for signal in signals}

        self.assertIn("question", kinds)

    def test_looks_like_chat_list_detects_badges_and_dense_timestamps(self):
        from wsa.parser import looks_like_chat_list

        chat_list = normalize_lines(
            "过气AI群\n10:57\n峰同学：［视频号］读书鉴世…\n"
            "［28条］\"马路\"撤回了一条.\n本溪首都校友群\n昨天 12:58\n"
            "［25条］商业航天网…\n家的小群\n06:45"
        )
        self.assertTrue(looks_like_chat_list(chat_list))
        self.assertFalse(looks_like_chat_list(normalize_lines("张昶\n下周三线下分享见\n老婆\n好的")))

    def test_parse_capture_never_guesses_icon_or_list_row_as_contact(self):
        # Chat-list OCR: status-bar debris first, then a search glyph, then
        # chat rows.  The guess must not pick "i、6•" or "Q".
        chat_list = parse_capture(
            "i、6•\nQ\n中欧移动互联网群（306）\n11:31\n［60条］脚印：太牛逼\n"
            "北交大创业和投资群\n11:21\n［7条］石锐：好的\n"
            "【国学会】\n11:01\n昨天 10:06\n［16条］蝶希般若\n"
            "过气AI群\n10:57\n［28条］\"马路\"撤回了一条."
        )
        self.assertEqual("微信会话列表", chat_list.contact_name)

        conversation = parse_capture("王志平\n我通过了你的朋友验证请求，现在我们可以开始聊天了")
        self.assertEqual("王志平", conversation.contact_name)


if __name__ == "__main__":
    unittest.main()
