---
name: wechat-social-assistant
description: "Use when the user wants a local-first WeChat relationship memory assistant: inspect wsa status, search contacts, summarize a contact, review relationship quality, record local feedback, draft follow-ups, use the MCP server, analyze recent visible WeChat captures, import screenshots, run or stop explicit watch mode, or export relationship notes to Obsidian."
---

# WeChat Social Assistant

Use this skill when the user asks to work with `wechat-social-assistant`, `wsa`, WeChat relationship memory, social follow-up drafts, Obsidian social-circle exports, or local WeChat OCR capture workflows.

## Safety Rules

- Never send WeChat messages automatically.
- Do not read or modify WeChat's private databases.
- Do not bypass platform protections, inject into WeChat, or scrape encrypted stores.
- Treat `watch`, `capture`, `import-image`, `ingest`, `feedback`, `analyze`, `export-obsidian`, `reset`, and `stop-watch` as write or process-control actions; explain the effect and get explicit user confirmation before running them.
- The MCP server is mostly read-only in v0.5. `record_feedback` is the only write tool and requires explicit user confirmation.
- Prefer read-only commands first: `wsa status`, `wsa contacts`, `wsa brief`, `wsa quality`, `wsa next`, and `wsa suggest`.
- Keep generated data local unless the user explicitly asks to publish, commit, or share it.

## Quick Start

1. Run `scripts/doctor.py --json` to inspect whether the local CLI, database, OCR helpers, and optional Obsidian paths are available.
2. If the CLI is missing, run `scripts/install_cli.sh` from a trusted checkout or ask the user before installing from GitHub.
3. Use `wsa status` to understand the current local memory before recommending actions.
4. In MCP-native environments, configure the stdio server command `wsa-mcp` or `python3 -m wsa.mcp_server`.
5. For a specific person or group, use `wsa contacts --query NAME`, then `wsa brief NAME`, `wsa quality --contact NAME`, or `wsa next --contact NAME`.
6. When the user reacts to a suggestion, record feedback with `wsa feedback NAME ACTION` after confirmation, then inspect it with `wsa feedback-list --contact NAME`.
7. For reports, use `wsa analyze` after user confirmation.
8. For Obsidian, use `wsa export-obsidian --vault PATH` after user confirmation.

## Common Commands

```bash
wsa status
wsa-mcp
python3 -m wsa.mcp_server
wsa contacts --query NAME
wsa brief NAME
wsa quality --contact NAME
wsa feedback-list --contact NAME
wsa feedback NAME too_pushy --note "draft was too direct"
wsa next --contact NAME
wsa suggest --contact NAME
wsa analyze
wsa export-obsidian --vault "$HOME/Documents/Obsidian Vault"
wsa import-image ./screenshot.png --contact NAME
wsa watch --interval 60
wsa stop-watch
```

## References

- Command details: `references/commands.md`
- Privacy and confirmation rules: `references/privacy.md`
- Recommended workflows: `references/workflows.md`
- Portable command wrapper: `scripts/wsa_run.py`
- Local environment self-check: `scripts/doctor.py`
