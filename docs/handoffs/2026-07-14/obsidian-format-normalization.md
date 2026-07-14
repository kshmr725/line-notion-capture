# Obsidian source formatting pass — 2026-07-14

## Scope

The canonical Obsidian vault remains `/Users/kevinwu/Desktop/Kevin_Brain`.
The `71_Food_美食與咖啡地圖` folder contains 27 Markdown notes. This pass
changed source formatting only; it did not rewrite the facts or move notes.

Mechanical fixes applied:

- removed one stray `yaml` line before frontmatter;
- fixed one `K#` H1 typo and ensured a blank line after frontmatter;
- converted nine indented `[!tip]` / `[!important]` lines to Obsidian callouts;
- updated the folder instruction so future notes use the same rules.

The four-field map summary keeps its single-line `<br>` separators as an
explicit Obsidian Map View compatibility exception. No other HTML is required
in the note body.

## Recovery

A byte-for-byte backup of the 27 notes and instruction file is stored at:

`/Users/kevinwu/Documents/Codex/2026-07-10/ji3/outputs/obsidian-format-backup-20260714/`

The Portal SQLite projection was backed up before an attempted semantic
re-index. The re-index provider returned `HTTPError` for all 44 documents, so
the projection was restored unchanged. Verification remains `valid: true`.

## Reader presentation

The Portal now renders the source Markdown subset safely for readers (headings,
bold/italic text, links, lists, and callouts) instead of exposing raw `#`, `**`,
or HTML syntax. This is a presentation layer only; Obsidian remains canonical.
