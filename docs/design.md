# WeChat Social Assistant MVP Design

## Goal

Build a local-first assistant that helps maintain relationships from visible WeChat desktop conversations without reading WeChat databases, injecting into WeChat, or sending messages automatically.

## Boundaries

- Capture only happens after an explicit CLI command or an explicitly started watch process.
- The tool stores raw OCR text, spatial observations, review decisions, and derived signals locally in SQLite.
- It does not decrypt, read, or modify WeChat's internal files.
- It does not send messages. It only writes suggested drafts for human review.

## Flow

1. User opens a WeChat conversation.
2. `wsa connectors` reports window/screen capture availability and Accessibility permission/AX reader readiness.
3. `wsa capture --contact NAME --mode accessibility` first reads the frontmost app's AX text tree; unavailable or empty AX data automatically falls back to frontmost-window Vision OCR. Both paths store the same structured observation contract.
4. `wsa ocr-review` lets the user accept, reject, or correct low-confidence observations without overwriting raw evidence.
5. `wsa suggest` generates a Markdown follow-up table with reasons and draft messages.
6. Optional `wsa watch` can run only when explicitly started; it records changed visible text while WeChat is frontmost.

## Data

SQLite tables:

- `people`: contact name and last interaction time.
- `captures`: raw OCR text, clean transcript, image path, source, and stable text hash.
- `ocr_observations`: one row per OCR line with confidence, normalized bounding box, source, and low-confidence speaker candidate.
- `ocr_reviews` / `ocr_review_events`: user-confirmed OCR review state and append-only review actions; `captures.corrected_text` is the effective analysis text.
- `capture_signals`: deterministic cues such as schedule, project, birthday, and needs-reply.
- `schema_migrations`: ordered database migration history.

## Safety

The default interaction is human-in-the-loop. The most automated mode still only observes the screen and writes local records. MCP file paths are constrained to a trusted root, and SQLite backups use the backup API. Network calls, automatic messaging, and WeChat database access are intentionally out of scope.
