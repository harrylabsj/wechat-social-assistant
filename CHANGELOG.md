# Changelog

All notable changes to WeChat Social Assistant are documented here.

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
