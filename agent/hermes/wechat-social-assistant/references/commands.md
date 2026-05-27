# wechat-social-assistant Commands

Use these commands through the local `wsa` CLI. Prefer read-only commands before running commands that mutate local state.

## Read-Only First

- `wsa status` - inspect database, screenshots, logs, and watch state.
- `wsa contacts --query NAME` - find known contacts, groups, speakers, organizations, and identity hints.
- `wsa brief NAME` - summarize one contact or matching set of contacts.
- `wsa next --contact NAME` - show the highest-priority follow-up draft for a contact.
- `wsa suggest --contact NAME` - render a follow-up suggestion table.
- `wsa profiles --contact NAME` - render contact-centered relationship profiles.

## MCP Read-Only Server

- `wsa-mcp` - run the MCP stdio server when the package console script is installed.
- `python3 -m wsa.mcp_server` - run the same MCP server from a source checkout.

The v0.3 MCP server exposes only read tools: `get_status`, `search_contacts`, `get_contact_brief`, `get_next_followup`, `get_daily_report`, and `list_recent_captures`. It also exposes `wsa://status`, `wsa://contacts`, `wsa://daily-report`, plus prompts for daily review, contact follow-up, and safe capture review.

## Confirm Before Running

- `wsa ingest --contact NAME --text TEXT` - adds manual text to the local database.
- `wsa import-image PATH --contact NAME` - OCRs screenshots and stores evidence.
- `wsa capture --contact NAME` - captures the screen or a selected window.
- `wsa watch --interval 60` - starts explicit foreground WeChat polling.
- `wsa stop-watch` - stops matching local watch processes.
- `wsa analyze` - refreshes derived data and writes report files.
- `wsa export-obsidian --vault PATH` - writes Markdown files into an Obsidian vault.
- `wsa reset --dry-run` then `wsa reset --yes` - previews or clears local memory.

## Wrapper

Use `scripts/wsa_run.py` when an agent needs a guardrail around command execution. It lists allowed commands with `--list-commands` and requires `--confirm` for write or process-control commands.
