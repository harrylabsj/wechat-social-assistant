# wechat-social-assistant Workflows

## Daily Review

1. Run `wsa status`.
2. Run `wsa next` for the top follow-up.
3. If the user asks for broader planning, run `wsa analyze` after confirmation.
4. Read `reports/outreach.md` and `reports/contact-profiles.md`.

## Contact Lookup

1. Run `wsa contacts --query NAME`.
2. Run `wsa brief NAME`.
3. If the draft is too weak or absent, run `wsa next --contact NAME --min-score 0`.

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
