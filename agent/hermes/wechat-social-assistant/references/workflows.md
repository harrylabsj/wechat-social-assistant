# wechat-social-assistant Workflows

## Daily Review

1. Run `wsa status`.
2. Run `wsa next` for the top follow-up.
3. If the user says the suggestion is done, irrelevant, too pushy, or useful, record that with `wsa feedback NAME ACTION` after confirmation.
4. If the user asks for broader planning, run `wsa analyze` after confirmation.
5. Read `reports/outreach.md` and `reports/contact-profiles.md`.

## Contact Lookup

1. Run `wsa contacts --query NAME`.
2. Run `wsa brief NAME`.
3. Run `wsa quality --contact NAME` when the user needs relationship strength, risks, gaps, and next action.
4. Run `wsa feedback-list --contact NAME` to inspect previous user preferences.
5. If the draft is too weak or absent, run `wsa next --contact NAME --min-score 0`.

## Feedback Loop

1. Confirm the user wants to record feedback locally.
2. Use `wsa feedback NAME ACTION`, where `ACTION` is one of `mark_done`, `snooze`, `not_relevant`, `too_pushy`, `good_draft`, `wrong_person`, `already_close`, or `do_not_contact`.
3. Use `wsa feedback-list --contact NAME` to verify the record.
4. Re-run `wsa next --contact NAME` or `wsa suggest --contact NAME` to see the adjusted recommendation.

## Group/Event Candidate Discovery

1. Run `wsa candidates --min-confidence 45` to review possible new people from groups and event-like contexts.
2. Explain that drafts are only suggestions and must not be sent automatically.
3. If the user wants to keep the queue, run `wsa candidates --sync` after confirmation.
4. If the user wants to promote one person, run `wsa candidate-confirm NAME --source-chat GROUP --yes` after confirmation.
5. Re-run `wsa brief NAME` or `wsa quality --contact NAME --min-score 0` to inspect the confirmed person.

## Screenshot Import

1. Confirm the user wants to import local screenshots.
2. Run `wsa import-image PATH --contact NAME`.
3. Run `wsa brief NAME` to verify the evidence landed on the intended contact.

## Obsidian Export

1. Confirm the vault path.
2. Run `wsa export-obsidian --vault PATH`.
3. Check `社交圈/人脉/索引.md` and `社交圈/分析报告/YYYY-MM-DD.md`.

## Explicit Watch Mode

1. Confirm the user wants automatic foreground WeChat capture.
2. Run `wsa watch --interval 60`.
3. Stop with `wsa stop-watch` or Ctrl-C.
4. Run `wsa status` after stopping.
