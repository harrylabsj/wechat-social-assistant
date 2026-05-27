# wechat-social-assistant for OpenClaw Without Plugins

OpenClaw can use `wechat-social-assistant` without a native plugin by treating `wsa` as a local CLI-backed agent capability. If the runtime supports MCP, it can also attach the stdio server.

## Install

From a trusted checkout:

```bash
python3 -m pip install -e .
```

From GitHub:

```bash
python3 -m pip install "git+https://github.com/harrylabsj/wechat-social-assistant.git"
```

## Operating Model

- Use `wsa status` before making recommendations.
- Use read-only commands for exploration: `contacts`, `brief`, `quality`, `candidates`, `weekly-report`, `feedback-list`, `next`, `suggest`, and `profiles`.
- For MCP-native operation, configure command `wsa-mcp` or `python3 -m wsa.mcp_server`; mutating tools require explicit confirmation.
- Ask before `feedback`, `candidate-confirm`, `candidates --sync`, MCP `record_feedback`, or MCP `confirm_relationship_candidate`.
- Ask for explicit user confirmation before commands that capture screenshots, import images, import/export Obsidian notes, write reports, reset memory, start watch mode, or stop processes.
- Keep all database, screenshot, and report files local unless the user explicitly asks to publish them.

## Suggested OpenClaw Prompt

```text
Use the local wechat-social-assistant CLI. Start with `wsa status`. Do not read WeChat private databases or send messages. Ask before running capture, watch, import-image, import-obsidian, analyze, export-obsidian, reset, or stop-watch.
```

## Useful Commands

```bash
wsa status
wsa contacts --query NAME
wsa brief NAME
wsa quality --contact NAME
wsa candidates --min-confidence 45
wsa candidate-confirm NAME --source-chat GROUP --yes
wsa weekly-report --date 2026-05-27
wsa feedback-list --contact NAME
wsa feedback NAME too_pushy --note "draft was too direct"
wsa next --contact NAME
wsa-mcp
python3 -m wsa.mcp_server
wsa analyze
wsa export-obsidian --vault "$HOME/Documents/Obsidian Vault"
wsa import-obsidian --vault "$HOME/Documents/Obsidian Vault" --dry-run
```
