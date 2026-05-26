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


if __name__ == "__main__":
    unittest.main()
