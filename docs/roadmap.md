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

## v0.5 Feedback Loop

- Local feedback actions: mark done, snooze, not relevant, too pushy, good draft, wrong person, already close, and do not contact.
- Use feedback to tune frequency, tone, thresholds, and draft style.

## v0.6 Group and Event Discovery

- Detect candidate relationships from group chats and event-like contexts.
- Model candidates as `candidate -> pending confirmation -> contact`.
- Preserve source group, evidence, confidence, and icebreaker draft.

## v0.7 Obsidian and Knowledge Base Depth

- Make Obsidian a two-way relationship memory surface.
- Improve daily and weekly relationship reports, information gaps, and manual enrichment.

## v0.8 Multi-Source Inputs

- Add local-first connectors in this order: contacts, calendar, Obsidian, meeting notes, then email.

## v0.9 Relationship Dashboard

- Provide a daily operating view: who to contact, why, what to say, cooling relationships, promising new people, unresolved commitments, high-value groups, and noisy groups.

## v1.0 Local Relationship OS

- Stable CLI, Hermes Skill, MCP server, Obsidian schema, database migrations, auditability, export/delete, explainable suggestions, and multi-source relationship memory.
