# wechat-social-assistant Commands

Use these commands through the local `wsa` CLI. Prefer read-only commands before running commands that mutate local state.

## Read-Only First

- `wsa status` - inspect database, screenshots, logs, and watch state.
- `wsa contacts --query NAME` - find known contacts, groups, speakers, organizations, and identity hints.
- `wsa brief NAME` - summarize one contact or matching set of contacts.
- `wsa quality --contact NAME` - render evidence-backed relationship quality, risks, gaps, and next actions.
- `wsa candidates --min-confidence 45` - discover group/event relationship candidates without writing by default.
- `wsa weekly-report --date YYYY-MM-DD` - render a weekly relationship report.
- `wsa feedback-list --contact NAME` - review auditable local feedback.
- `wsa next --contact NAME` - show the highest-priority follow-up draft for a contact.
- `wsa suggest --contact NAME` - render a follow-up suggestion table.
- `wsa profiles --contact NAME` - render contact-centered relationship profiles.

## MCP Read-Only Server

- `wsa-mcp` - run the MCP stdio server when the package console script is installed.
- `python3 -m wsa.mcp_server` - run the same MCP server from a source checkout.

The v0.7 MCP server exposes read tools: `get_status`, `search_contacts`, `get_contact_brief`, `get_next_followup`, `get_daily_report`, `get_weekly_report`, `get_relationship_quality`, `list_relationship_candidates`, `list_feedback`, and `list_recent_captures`. Write tools are `record_feedback` and `confirm_relationship_candidate`, and both require explicit confirmation arguments. It also exposes `wsa://status`, `wsa://contacts`, `wsa://daily-report`, `wsa://weekly-report`, `wsa://relationship-quality`, `wsa://relationship-candidates`, plus prompts for daily review, weekly review, contact follow-up, relationship candidate review, and safe capture review.

## Confirm Before Running

- `wsa ingest --contact NAME --text TEXT` - adds manual text to the local database.
- `wsa candidates --sync` - persists discovered candidates to the local pending queue.
- `wsa candidate-confirm NAME --source-chat GROUP --yes` - promotes a reviewed candidate to confirmed.
- `wsa feedback NAME ACTION` - records user feedback such as `mark_done`, `snooze`, `too_pushy`, or `good_draft`.
- `wsa import-image PATH --contact NAME` - OCRs screenshots and stores evidence.
- `wsa import-obsidian --vault PATH --yes` - imports manual enrichment edited in Obsidian contact notes.
- `wsa capture --contact NAME` - captures the screen or a selected window.
- `wsa watch --interval 60` - starts explicit foreground WeChat polling.
- `wsa stop-watch` - stops matching local watch processes.
- `wsa analyze` - refreshes derived data and writes report files.
- `wsa export-obsidian --vault PATH` - writes Markdown files into an Obsidian vault.
- `wsa reset --dry-run` then `wsa reset --yes` - previews or clears local memory.

## Wrapper

Use `scripts/wsa_run.py` when an agent needs a guardrail around command execution. It lists allowed commands with `--list-commands` and requires `--confirm` for write or process-control commands.
