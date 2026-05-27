# wechat-social-assistant Roadmap

`wechat-social-assistant` is evolving into a local-first personal relationship operating system. The CLI remains the stable core; agent ecosystems use thin adapters around it.

## v0.2 Agent Foundation - shipped

- Hermes Skill with privacy guardrails, command guidance, and UI metadata.
- OpenClaw non-plugin usage guide.
- Cross-ecosystem `agent/agent.json` manifest.
- Portable doctor and guarded CLI wrapper scripts.

## v0.3 MCP Interface - shipped

- Read-only MCP tools: status, contact search, contact brief, next follow-up, daily report, and recent captures.
- MCP resources: `wsa://status`, `wsa://contacts`, and `wsa://daily-report`.
- MCP prompts: daily relationship review, contact follow-up, and safe capture review.
- Write operations remain outside MCP in v0.3; they use confirmed CLI commands until prepare/apply write tools are introduced later.

## v0.4 Relationship Quality Layer - shipped

- Explainable relationship strength, recency, context, reciprocity, risks, information gaps, and next action.
- Every score must cite local evidence.
- CLI `quality` renders a relationship operating desk.
- MCP `get_relationship_quality` and `wsa://relationship-quality` expose the same read-only quality layer to agent ecosystems.

## v0.5 Feedback Loop - shipped

- Local feedback actions: mark done, snooze, not relevant, too pushy, good draft, wrong person, already close, and do not contact.
- Use feedback to tune frequency, tone, thresholds, and draft style.
- CLI `feedback` and `feedback-list` provide an auditable local feedback log.
- Suggestions suppress done/snoozed/not relevant/do-not-contact items and tune draft tone/score from `too_pushy` and `good_draft`.
- MCP `record_feedback` is the only v0.5 write tool and requires explicit confirmation.

## v0.6 Group and Event Discovery - shipped

- Detect candidate relationships from group chats and event-like contexts.
- Model candidates as `candidate -> pending confirmation -> contact`.
- Preserve source group, evidence, confidence, and icebreaker draft.
- CLI `candidates` renders local candidate people; `candidates --sync` persists the pending queue; `candidate-confirm --yes` promotes a candidate after review.
- MCP `list_relationship_candidates` is read-only; `confirm_relationship_candidate` requires explicit confirmation.

## v0.7 Obsidian and Knowledge Base Depth - shipped

- Make Obsidian a two-way relationship memory surface.
- Improve daily and weekly relationship reports, information gaps, and manual enrichment.
- CLI `import-obsidian` imports user-edited `社交圈/人脉/*.md` manual enrichment into local `contact_enrichments`.
- `export-obsidian` writes editable manual enrichment blocks, daily reports, and weekly reports.
- MCP `get_weekly_report` and `wsa://weekly-report` expose weekly analysis read-only.

## v0.8 Multi-Source Inputs - shipped

- Add local-first imports for contacts, calendar, Obsidian people notes, meeting notes, and email files.
- Store imported evidence in `relationship_sources` and merge it into contact-centered profiles, briefs, quality cards, reports, and search.
- CLI `import-source` previews with `--dry-run` and requires `--yes` before writing local data.
- CLI `sources` lists source evidence by contact or source type.
- MCP `list_relationship_sources` and `wsa://relationship-sources` expose imported evidence read-only.

## v0.9 Relationship Dashboard - shipped

- Provide a daily relationship dashboard: priority follow-ups, cooling contacts, candidate opportunities, open commitments, high-value groups, noisy groups, and fresh source updates.
- CLI `dashboard` renders the operating view in Markdown.
- MCP `get_relationship_dashboard` and `wsa://relationship-dashboard` expose the dashboard read-only to agent ecosystems.

## v1.0 Local Relationship OS

- Stable CLI, Hermes Skill, MCP server, Obsidian schema, database migrations, auditability, export/delete, explainable suggestions, and multi-source relationship memory.
