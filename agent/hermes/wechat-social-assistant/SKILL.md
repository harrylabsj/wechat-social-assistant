---
name: wechat-social-assistant
description: "Use when the user wants a local-first WeChat relationship memory assistant: inspect wsa status, search contacts, summarize a contact, review the relationship dashboard or quality layer, discover group/event relationship candidates, review weekly reports, import local relationship sources, import/export Obsidian relationship notes, record local feedback, draft follow-ups, use the MCP server, analyze recent visible WeChat captures, import screenshots, or run/stop explicit watch mode."
---

# WeChat Social Assistant

Use this skill when the user asks to work with `wechat-social-assistant`, `wsa`, WeChat relationship memory, social follow-up drafts, Obsidian social-circle exports, or local WeChat OCR capture workflows.

## Safety Rules

- Never send WeChat messages automatically.
- Do not read or modify WeChat's private databases.
- Do not bypass platform protections, inject into WeChat, or scrape encrypted stores.
- Treat `watch`, `capture`, `import-image`, `ingest`, `feedback`, `candidate-confirm`, `candidates --sync`, `import-obsidian`, `import-source`, `analyze`, `export-obsidian`, `reset`, and `stop-watch` as write or process-control actions; explain the effect and get explicit user confirmation before running them.
- The MCP server is mostly read-only in v0.9. `record_feedback` and `confirm_relationship_candidate` are write tools and require explicit user confirmation.
- Prefer read-only commands first: `wsa status`, `wsa dashboard`, `wsa contacts`, `wsa brief`, `wsa quality`, `wsa candidates`, `wsa sources`, `wsa weekly-report`, `wsa next`, and `wsa suggest`.
- Keep generated data local unless the user explicitly asks to publish, commit, or share it.

## Quick Start

1. Run `scripts/doctor.py --json` to inspect whether the local CLI, database, OCR helpers, and optional Obsidian paths are available.
2. If the CLI is missing, run `scripts/install_cli.sh` from a trusted checkout or ask the user before installing from GitHub.
3. Use `wsa status` to understand the current local memory before recommending actions.
4. In MCP-native environments, configure the stdio server command `wsa-mcp` or `python3 -m wsa.mcp_server`.
5. For daily planning, use `wsa dashboard`.
6. For a specific person or group, use `wsa contacts --query NAME`, then `wsa brief NAME`, `wsa quality --contact NAME`, or `wsa next --contact NAME`.
7. To grow the network from groups/events, run `wsa candidates`; only run `wsa candidates --sync` or `wsa candidate-confirm NAME --source-chat GROUP --yes` after confirmation.
8. When the user reacts to a suggestion, record feedback with `wsa feedback NAME ACTION` after confirmation, then inspect it with `wsa feedback-list --contact NAME`.
9. For weekly planning, use `wsa weekly-report`.
10. To merge local sources such as vCard, ICS, notes, Obsidian people notes, or EML files, preview with `wsa import-source PATH --dry-run`, then import with `wsa import-source PATH --yes` after confirmation.
11. For reports, use `wsa analyze` after user confirmation.
12. For Obsidian export/import, use `wsa export-obsidian --vault PATH` or `wsa import-obsidian --vault PATH --yes` after user confirmation.

## Common Commands

```bash
wsa status
wsa-mcp
python3 -m wsa.mcp_server
wsa contacts --query NAME
wsa brief NAME
wsa dashboard
wsa quality --contact NAME
wsa candidates --min-confidence 45
wsa candidate-confirm NAME --source-chat GROUP --yes
wsa sources --contact NAME
wsa import-source ./contacts.vcf --dry-run
wsa import-source ./contacts.vcf --yes
wsa weekly-report --date 2026-05-27
wsa feedback-list --contact NAME
wsa feedback NAME too_pushy --note "draft was too direct"
wsa next --contact NAME
wsa suggest --contact NAME
wsa analyze
wsa export-obsidian --vault "$HOME/Documents/Obsidian Vault"
wsa import-obsidian --vault "$HOME/Documents/Obsidian Vault" --yes
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
