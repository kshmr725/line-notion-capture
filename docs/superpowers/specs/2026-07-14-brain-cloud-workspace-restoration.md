# Brain Cloud Workspace Restoration

Date: 2026-07-14

Status: approved from the July 10 Cloud Shell visual companion and the user's explicit overnight delivery request.

## Outcome

Replace the generic editorial Portal with a compact, Chinese-first Second Brain workbench. The Portal remains read-only; Obsidian and Notion remain canonical editing surfaces.

## Signed visual source

`/Users/kevinwu/.codex/visualizations/2026/07/10/019f4a0f-624b-7e82-a3c6-4bf99fa233c1/cloud-shell-views.html` is the visual and interaction source of truth. Its desktop rail, top search, compact Cloud tiles, recent-content rows, Web3 matrix, Food map-or-list composition, and responsive collapse must be recognisable in the delivered Portal.

## Non-negotiable experience

- Desktop uses a persistent Cloud rail: 首頁, Web3 商業研究, 美食與咖啡地圖, AI 自動化, plus a secondary source-status link.
- Every page uses the same app shell. Remove the oversized hero, decorative timeline, generic directory prose, and large empty cards.
- Home opens with one global search field, then real Cloud tiles and a compact cross-Cloud 「繼續使用」 list. Counts and freshness derive from indexed items; an empty Cloud says 「尚未索引」.
- Knowledge cards lead with title, useful summary, Cloud/type, and freshness. Card clicks open the item; canonical-source actions remain secondary.
- Web3 has URL-backed context tabs, a sector/concept matrix based only on real indexed concepts, latest research, and cross-Cloud concept links.
- Food shows a map only if real coordinates exist; otherwise it presents an honest list-first discovery panel. Place rows expose only stored area/category/visit/use-case data.
- AI has a distinct Tool / Agent / MCP / Workflow / Reliability orientation and never reuses the Food or Web3 layout unchanged.
- Item, search, place, and sync views inherit the shell and use Chinese-first task copy. Obsidian items retain 「在 Obsidian 開啟」; Notion items retain 「在 Notion 編輯」.
- At <= 620px the rail becomes compact horizontal navigation, grids collapse safely, and all targets remain at least 44px.

## Data truth and degraded operation

- Do not hard-code sample counts, freshness, sector status, map positions, or AI previews.
- When Gemini embeddings are unavailable, the explicit `--lexical-only` index command stores the normal item and FTS projection without embeddings. It must report a successful lexical-only index and leave AI answers visibly source-only; it must never pretend semantic search is active.
- Existing semantic indexing keeps its atomic projection behavior. Lexical-only mode is opt-in at the command boundary, not a silent fallback for an otherwise semantic run.

## Acceptance

- A user reaches a Cloud in one click, searches immediately, and opens a real note in at most three interactions.
- No marketing layout elements remain in Portal templates or CSS.
- Each Cloud page has a data-derived, domain-specific workspace and no dead tab/control.
- Empty and degraded states are honest and usable.
- Existing tenant, canonical-link, query-limit, accessibility, and source-only guarantees continue to pass.
