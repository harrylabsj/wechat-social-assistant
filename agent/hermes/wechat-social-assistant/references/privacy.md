# wechat-social-assistant Privacy Rules

`wechat-social-assistant` is local-first. It works from visible WeChat screenshots, OCR text, manual notes, and user-provided image imports.

## Hard Boundaries

- Do not read WeChat private databases.
- Do not decrypt, patch, inject into, or automate the WeChat app.
- Do not send messages automatically.
- Do not publish screenshots, database files, logs, or Obsidian exports unless the user explicitly asks.
- Do not run `watch`, `capture`, `import-image`, `ingest`, `analyze`, `export-obsidian`, `reset`, or `stop-watch` without explaining the effect and getting confirmation.

## Local Data

Default local paths are:

- Database: `data/social.db`
- Screenshots: `data/captures`
- Watch log: `data/watch.log`
- Generated reports: `reports`
- Optional Obsidian export: user-selected vault under `社交圈`

These paths are intentionally ignored by git in the public project.

## Audit Habit

Before and after mutating commands, run `wsa status`. For risky cleanup, run dry-run first, for example `wsa reset --dry-run`.
