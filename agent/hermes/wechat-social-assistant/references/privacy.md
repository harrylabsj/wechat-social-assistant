# wechat-social-assistant Privacy Rules

`wechat-social-assistant` is local-first. It works from visible WeChat screenshots, OCR text, manual notes, user-provided image imports, and user-provided local relationship source files.

## Hard Boundaries

- Do not read WeChat private databases.
- Do not decrypt, patch, inject into, or automate the WeChat app.
- Do not send messages automatically.
- Do not publish screenshots, database files, logs, or Obsidian exports unless the user explicitly asks.
- Do not run `watch`, `capture`, `captures-dir PATH/--clear/--create`, `import-image`, `ingest`, `feedback`, `candidate-confirm`, `candidates --sync`, `import-obsidian`, `import-source`, `export-data`, `privacy purge --yes`, `backup --encrypt`, `delete-contact`, `analyze`, `export-obsidian`, `reset`, or `stop-watch` without explaining the effect and getting confirmation.
- MCP `capture_commit`, `record_feedback`, `confirm_relationship_candidate`, `record_ocr_review`, non-dry-run `purge_expired_captures`, and `create_encrypted_backup` are writes. Use them only after explicit user confirmation with the required `confirmation_text`.

## Local Data

Default local paths are:

- Database: `data/social.db`
- Screenshots: configured capture root; macOS checkouts use iCloud Drive when mounted, otherwise `data/captures`
- Watch log: `data/watch.log`
- Feedback: `contact_feedback` rows inside `data/social.db`
- Relationship candidates: `relationship_candidates` rows inside `data/social.db`
- Manual enrichment: `contact_enrichments` rows inside `data/social.db`
- Relationship sources: `relationship_sources` rows inside `data/social.db`
- Generated reports: `reports`
- Optional Obsidian export: user-selected vault under `社交圈`
- Optional JSON export: user-selected path from `export-data`
- Raw evidence is local-only by default; JSON exports are redacted unless `--raw` is explicitly requested.
- Default capture retention is 90 days. Run `wsa privacy purge --dry-run` before deletion; only WSA-managed, unshared screenshots can be removed.
- Use `wsa captures-dir` to inspect the active root. SQLite stays local; switching roots affects new captures and historical local WSA screenshots remain compatible during migration.

These paths are intentionally ignored by git in the public project.

## Audit Habit

Before and after mutating commands, run `wsa status` or `wsa audit`. For risky cleanup, run dry-run first, for example `wsa delete-contact NAME --dry-run` or `wsa reset --dry-run`.
