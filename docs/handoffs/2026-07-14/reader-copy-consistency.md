# Reader copy consistency — 2026-07-14

## Scope

The portal now has one reader-facing copy contract across Home, Cloud workspaces,
search results, item pages, and place pages. Canonical Obsidian titles and
content remain unchanged; normalization happens only in the presentation layer.

## Decisions

- Cloud descriptions are short, action-oriented Chinese sentences and are
  shared by the Home Cloud cards and each Cloud workspace.
- Exploration links use the same Chinese task language as Home intents; internal
  English schema names stay out of visible controls.
- List/card subtitles use `reader_summary()` rather than raw source summaries.
  Place summaries use a stable order: 評價 → 地址 → 營業時間 → 價位／特色.
- Public Cloud badges use `public_cloud_label()` (`Web3`, `美食地圖`, `AI 自動化`)
  instead of storage keys such as `ai` or `food`.
- `clean_display_text()` removes HTML, Markdown emphasis, Obsidian wikilinks,
  heading markers, and hash tags before short text is rendered.
- Place actions are reader-facing (`查看原始筆記`, `在 Google 地圖查看`).

## Evidence

- Commit: `f442d96 fix: normalize reader-facing portal copy`
- Tests: `242 passed`; `git diff --check` clean.
- Database verification: `scripts/verify_brain_portal.py` returned `valid: true`,
  44 items, no stale syncs, no tenant leaks, and no unsafe canonical refs.
- Local smoke checks on `/`, `/cloud/ai`, and a real `/place/...` route confirmed
  localized Cloud descriptions, normalized place facts, and no raw `[[wikilink]]`
  or `#tag` syntax in card subtitles.
