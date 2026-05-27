# wechat-social-assistant for OpenClaw Without Plugins

OpenClaw can use `wechat-social-assistant` without a native plugin by treating `wsa` as a local CLI-backed agent capability. If the runtime supports MCP, it can also attach the read-only stdio server.

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
- Use read-only commands for exploration: `contacts`, `brief`, `quality`, `next`, `suggest`, and `profiles`.
- For MCP-native operation, configure command `wsa-mcp` or `python3 -m wsa.mcp_server`; v0.4 MCP tools are read-only.
- Ask for explicit user confirmation before commands that capture screenshots, import images, write reports, export to Obsidian, reset memory, start watch mode, or stop processes.
- Keep all database, screenshot, and report files local unless the user explicitly asks to publish them.

## Suggested OpenClaw Prompt

```text
Use the local wechat-social-assistant CLI. Start with `wsa status`. Do not read WeChat private databases or send messages. Ask before running capture, watch, import-image, analyze, export-obsidian, reset, or stop-watch.
```

## Useful Commands

```bash
wsa status
wsa contacts --query NAME
wsa brief NAME
wsa quality --contact NAME
wsa next --contact NAME
wsa-mcp
python3 -m wsa.mcp_server
wsa analyze
wsa export-obsidian --vault "$HOME/Documents/Obsidian Vault"
```
