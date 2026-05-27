---
name: wechat-social-assistant
description: "Use when the user wants a local-first WeChat relationship memory assistant: inspect wsa status, search contacts, summarize a contact, draft follow-ups, analyze recent visible WeChat captures, import screenshots, run or stop explicit watch mode, or export relationship notes to Obsidian."
---

# WeChat Social Assistant

Use this skill when the user asks to work with `wechat-social-assistant`, `wsa`, WeChat relationship memory, social follow-up drafts, Obsidian social-circle exports, or local WeChat OCR capture workflows.

## Safety Rules

- Never send WeChat messages automatically.
- Do not read or modify WeChat's private databases.
- Do not bypass platform protections, inject into WeChat, or scrape encrypted stores.
- Treat `watch`, `capture`, `import-image`, `ingest`, `analyze`, `export-obsidian`, `reset`, and `stop-watch` as write or process-control actions; explain the effect and get explicit user confirmation before running them.
- Prefer read-only commands first: `wsa status`, `wsa contacts`, `wsa brief`, `wsa next`, and `wsa suggest`.
- Keep generated data local unless the user explicitly asks to publish, commit, or share it.

## Quick Start

1. Run `scripts/doctor.py --json` to inspect whether the local CLI, database, OCR helpers, and optional Obsidian paths are available.
2. If the CLI is missing, run `scripts/install_cli.sh` from a trusted checkout or ask the user before installing from GitHub.
3. Use `wsa status` to understand the current local memory before recommending actions.
4. For a specific person or group, use `wsa contacts --query NAME`, then `wsa brief NAME` or `wsa next --contact NAME`.
5. For reports, use `wsa analyze` after user confirmation.
6. For Obsidian, use `wsa export-obsidian --vault PATH` after user confirmation.

## Common Commands

```bash
wsa status
wsa contacts --query NAME
wsa brief NAME
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
