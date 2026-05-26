# WeChat Social Assistant MVP Design

## Goal

Build a local-first assistant that helps maintain relationships from visible WeChat desktop conversations without reading WeChat databases, injecting into WeChat, or sending messages automatically.

## Boundaries

- Capture only happens after an explicit CLI command.
- The tool stores OCR text and derived signals locally in SQLite.
- It does not decrypt, read, or modify WeChat's internal files.
- It does not send messages. It only writes suggested drafts for human review.

## Flow

1. User opens a WeChat conversation.
2. `wsa capture --contact NAME` screenshots the selected window, OCRs it with macOS Vision, and stores clean text.
3. `wsa suggest` generates a Markdown follow-up table with reasons and draft messages.
4. Optional `wsa watch` can run only when explicitly started; it records changed visible text while WeChat is frontmost.

## Data

SQLite tables:

- `people`: contact name and last interaction time.
- `captures`: raw OCR text, clean transcript, image path, source, and stable text hash.
- `capture_signals`: deterministic cues such as schedule, project, birthday, and needs-reply.

## Safety

The default interaction is human-in-the-loop. The most automated mode still only observes the screen and writes local records. Network calls, automatic messaging, and WeChat database access are intentionally out of scope.
