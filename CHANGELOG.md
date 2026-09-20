# Changelog

All notable changes to WeChat Social Assistant are documented here.

## 1.4.5 - 2026-09-20

Security and data-safety release. Upgrade is strongly recommended.

### Fixed — dashboard rendering

- Renaming the HTML escaper to `text()` collided with render-local `const
  text` elements in the timeline and draft list: with at least one outreach
  draft, every dashboard poll threw `TypeError` and stopped rendering. The
  shadowed elements are renamed and a static test keeps the helper unique.
- The dashboard now sends `X-Frame-Options: DENY` and
  `Content-Security-Policy: frame-ancestors 'none'` — the CSRF token lives in
  the page itself, so a framing defense is required against clickjacking.
- Concurrent dashboard saves of the same contact no longer overwrite each
  other: the field merge runs inside one `BEGIN IMMEDIATE` transaction.

### Fixed — permission safety

- `backup --out`, `export-data --out` and encrypted backups no longer chmod
  user-chosen directories to `0700` (`wsa export-data --out /tmp/a.json`
  previously turned `/tmp` owner-only). Only directories WSA itself owns are
  tightened; a user's output file is secured directly.
- Exports and encrypted backups write through an owner-only temporary file,
  so an interrupted run can no longer leave a group/world-readable file, and
  screenshots are created `0600` like every other data file.

### Fixed — data safety

- `owned_capture_images` compares references as resolved paths (the same file
  written as `~/...` and as an absolute path counts as one file), chunks the
  id list past SQLite's host-parameter limit, and the v1 migration marks
  pre-migration screenshots as WSA-managed so retention can retire them.
- New `wsa captures-dir --purge-orphans [--yes]` retires screenshots no
  capture row references anymore (crash-window leftovers). Reset still never
  touches them; this is the explicit, separately confirmed way.

### Fixed — reliability

- Every `ocr.py` helper process (`screencapture`, Vision OCR, frontmost,
  `sips`, `osascript`) now runs with a hard timeout; a hung helper ends the
  capture cycle instead of stalling the watch loop forever.
- Swift helpers compile to a temporary file and rename into place, so a
  killed or concurrent build can never leave a half-written binary that the
  mtime check would trust.
- The watch failure branches log defensively: a full disk or closed stderr
  can no longer defeat the catch-all and kill the watcher.
- `import-image` failure branches exit `2` instead of `0`, so scripts can
  detect a failed import.

### Fixed — MCP

- A JSON-RPC line that is valid JSON but not an object gets a protocol error
  response instead of ending the server (hosts previously saw only EOF).
- Expected capture failures are reported as tool errors (`isError: true`)
  instead of misleading `Invalid params` / `Internal error` codes.
- `wsa-mcp --db` pins the database process-wide, `WSA_MCP_ENFORCE_PATHS`
  cannot be silently downgraded by an inherited `0`, `get_status` resolves
  `captures_dir` under the media policy, and `list_outreach_drafts` clamps
  its default limit the same way as explicit ones.

### Fixed — parsing and pipelines

- An unparseable email `Date` header no longer stores its raw string (which
  crashed the whole suggestion pipeline and skewed string-ordered "latest
  interaction" comparisons); the person simply yields no suggestion.
- ICS timestamps ending in `Z` keep their UTC offset instead of `rstrip`
  silently dropping it; vCard names encoded as QUOTED-PRINTABLE (`=E5=...`)
  are decoded instead of imported as mojibake contacts.
- Unmatched archive files still land in `relationship_sources` under their
  topic bucket, but the bucket's people row never gains a
  `last_interaction_at`, so bucket labels stop appearing as contacts with
  drafts in suggestions and profiles.
- Sent and dismissed outreach drafts are terminal: they cannot be
  re-approved, edited, re-sent or dismissed again.
- One person who is both a direct contact and a group speaker yields one
  suggestion (higher score wins) instead of two.
- Short conversational replies (「好的」「收到」 and particle-suffixed lines)
  no longer become "name hints" — and are no longer deleted from profiles as
  duplicates of one.
- Obsidian imports skip unreadable notes instead of aborting, and skip
  same-name duplicates instead of silently overwriting the first note's
  fields.
- `WSA_CAPTURES_DIR` relative paths anchor at the database directory, so
  watch and purge started from different working directories agree on where
  screenshots live; the archive manifest default honours
  `WSA_ARCHIVE_MANIFEST`.

### Fixed — data loss (from the 2026-09-03 review, unreleased until now)

- `reset` deleted **every** image file in the resolved screenshot directory
  rather than the screenshots the target database owns. With `WSA_CAPTURES_DIR`
  exported (the standalone installer does this), `wsa reset --yes --db
  /tmp/scratch.db` wiped the real screenshot library, and so did any test that
  exercised the reset path. Reset now deletes only files that the database's
  own captures reference, carry the `image_managed` ownership bit, resolve
  inside a managed capture root, and no other capture still references — the
  rule `delete-contact` and retention purge already used. User-imported images
  and unreferenced files are preserved.
- `reset` now prints the database path, the capture directory and a sample of
  the files it will remove, in both `--dry-run` and confirmed runs.
- The ownership rule lives in one place (`store.owned_capture_images`) instead
  of three near-copies.

### Fixed — test isolation

- The test suite inherited `WSA_*` from the developer's shell, so tests
  resolved the real database and screenshot directory. `tests/_env_guard.py`
  now scrubs those variables before `wsa` is imported in every test module,
  and a hygiene test fails if a module skips the guard.

### Fixed — privacy

- Removed real contact names, chat fragments and the in-repo denylist of
  private terms from the published tree. The release hygiene test now checks a
  git-ignored `.private-denylist` instead, and enforces a positive allowlist of
  placeholder fixture names.
- Added `MANIFEST.in` so the source distribution no longer ships the test suite.
- Local data is created owner-only: `0700` directories, `0600` database,
  screenshots, settings, logs, reports and exports. Both installers set
  `umask 077`.

### Fixed — dashboard security

- The local dashboard rejected nothing sent by a browser: any page could POST
  to it, and a DNS-rebinding page could read every contact timeline. It now
  validates `Host`/`Origin`, requires `Content-Type: application/json` and a
  per-session token on writes, and sends `Cross-Origin-Resource-Policy`.
- The CRM view reuses one profile build instead of three per poll, bounds its
  capture scan, and stops polling while the tab is hidden.

### Fixed — reliability (from the 2026-09-03 review)

- `watch` no longer exits on an unexpected error (full disk, locked database,
  missing helper); it logs and continues.
- Missing Xcode Command Line Tools now reports `xcode-select --install`
  instead of a bare `FileNotFoundError` on first capture.
- Failed automated captures (watch, MCP) delete the screenshot they created;
  one-shot `capture`/`quick-capture` keep it, controlled by
  `--keep-failed-image` / `--no-keep-failed-image`.
- `watch.log` rotates at 5 MB instead of growing without bound.
- `stop-watch` prints the database each matched process names, and says when a
  process carries no `--db` and therefore matches any selection.

### Fixed — MCP and crypto (from the 2026-09-03 review)

- Encrypted backups use PBKDF2 with 600,000 iterations instead of OpenSSL's
  10,000 default; `wsa backup --encrypt` prints the matching decrypt command.
  **Backups created before 1.4.5 still decrypt with the old default.**
- `create_encrypted_backup` only accepts a `WSA_`-prefixed passphrase variable,
  so a caller cannot select one whose value it already knows.
- The MCP capture root is trusted for media arguments only, not for database,
  export or backup paths; an unconfigured `wsa-mcp` defaults its trusted root
  to the database directory rather than the working directory.
- Retention cutoffs parse naive timestamps as local time, matching the rest of
  the codebase, instead of silently treating them as UTC.

## 1.4.4 - 2026-08-27

- Fixed contact attribution for full WeChat window screenshots: Vision OCR
  now uses the right-panel title bounds to recover the selected private chat
  even when the left session list contains many timestamps and unread badges.
- Added regression coverage for the “示例联系人” private-chat capture shape.

## 1.4.3 - 2026-08-27

- Added a CRM dashboard notice when captures contain only the WeChat session
  list or other non-conversation UI, explaining how to collect contact
  timelines from a specific chat window.
- Exposed capture count in the CRM summary so successful screenshots are
  visible even when no contact record can be derived.

## 1.4.2 - 2026-08-26

- Added a standalone one-line installer for PyPI users without a source
  checkout; it creates the data directory, virtual environment, shell env,
  database, and local screenshot directory.
- Made `WSA_DB` a supported default database override for installed CLI/MCP
  commands.
- Kept iCloud capture storage opt-in for standalone users via `--icloud` or
  `WSA_USE_ICLOUD=1`; local storage is the default.

## 1.4.1 - 2026-08-26

- Removed machine-specific path sentinels from the public test suite and
  republished the package with privacy-safe source distribution contents.
- Added explicit Apache-2.0 package metadata, security guidance, and release
  hygiene documentation.

## 1.4.0 - 2026-08-24

- Added the contact-centric local CRM dashboard with conversation timelines,
  derived summaries, relationship signals, and follow-up context.
- Added configurable iCloud/local screenshot storage and migration-safe path
  handling while keeping SQLite and logs local.
- Added accessibility-first capture, ScreenCaptureKit/window OCR fallback,
  perception diagnostics, privacy retention, redacted export, and encrypted
  backup controls.
- Added MCP and agent adapters for Hermes and OpenClaw with explicit
  confirmation gates for capture, writes, deletion, and outreach drafts.
