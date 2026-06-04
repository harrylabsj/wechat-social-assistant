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

- Use `wsa status` or `wsa audit` before making recommendations.
- Use read-only commands for exploration: `audit`, `dashboard`, `cockpit --dry-run`, `contacts`, `brief`, `quality`, `candidates`, `sources`, `weekly-report`, `feedback-list`, `next`, `suggest`, and `profiles`.
- For MCP-native operation, configure command `wsa-mcp` or `python3 -m wsa.mcp_server`; mutating tools require explicit confirmation.
- Ask before `feedback`, `candidate-confirm`, `candidates --sync`, MCP `record_feedback`, or MCP `confirm_relationship_candidate`.
- Ask for explicit user confirmation before commands that capture screenshots, quick-capture visible conversations, set watch intervals, import images, import local relationship source files, import WeChat archive manifests, build the writing cockpit, export/delete local data, import/export Obsidian notes, write reports, reset memory, start watch mode, or stop processes.
- Keep all database, screenshot, and report files local unless the user explicitly asks to publish them.

## Suggested OpenClaw Prompt

```text
Use the local wechat-social-assistant CLI. Start with `wsa status` and `wsa audit`. Do not read WeChat private databases or send messages. Ask before running capture, quick-capture, watch-interval, watch, import-image, import-source, import-wechat-archive, cockpit --yes, export-data, delete-contact, import-obsidian, analyze, export-obsidian, reset, or stop-watch.
```

## Useful Commands

```bash
wsa status
wsa audit
wsa dashboard
wsa cockpit --dry-run
wsa cockpit --vault "$HOME/Hbrain" --yes --replace-wechat-archive
wsa contacts --query NAME
wsa brief NAME
wsa quality --contact NAME
wsa candidates --min-confidence 45
wsa candidate-confirm NAME --source-chat GROUP --yes
wsa sources --contact NAME
wsa import-source ./contacts.vcf --dry-run
wsa import-wechat-archive --dry-run
wsa export-data --out ./wsa-export.json --yes
wsa delete-contact NAME --dry-run
wsa weekly-report --date 2026-05-27
wsa feedback-list --contact NAME
wsa feedback NAME too_pushy --note "draft was too direct"
wsa next --contact NAME
wsa-mcp
python3 -m wsa.mcp_server
wsa analyze
wsa export-obsidian --vault "$HOME/Documents/Obsidian Vault"
wsa import-obsidian --vault "$HOME/Documents/Obsidian Vault" --dry-run
wsa quick-capture
wsa watch-interval 10
```
