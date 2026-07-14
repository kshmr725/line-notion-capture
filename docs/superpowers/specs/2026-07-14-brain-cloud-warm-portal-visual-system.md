# Brain Cloud Warm Portal Visual System

Date: 2026-07-14

Status: Approved by Kevin in the visual comparison companion

Task: `2026-07-14-brain-cloud-zero-cost-beta`

## 1. Decision and scope

The Portal keeps the approved Cloud-shell information architecture from the supplied screenshot:

1. predictable Brain Cloud navigation;
2. a home search and Cloud entry points;
3. Web3 and Food as separate task-oriented workspaces;
4. a Web3 sector map before research details;
5. an interactive Food map paired with a place list;
6. nearby cross-Cloud concept connections.

It does **not** keep the screenshot's visual palette as the product palette. The approved direction is
**warm paper, charcoal, and amber**. The recovered prior source proves the warm-paper and amber
tokens below; the accidental green restoration is rejected. Blue is reserved for system semantics,
not a second brand color.

This document supersedes only visual and presentation requirements in
`2026-07-14-brain-cloud-zero-cost-beta.md` and the visual/global-token portions of
`2026-07-14-brain-cloud-truthful-ui-map.md`. Source truth, tenancy, access controls, data models,
and map-coordinate requirements remain unchanged.

## 2. Token contract

| Token | Value | Meaning |
| --- | --- | --- |
| `--portal-canvas` | `#F4F2ED` | warm page field; never green or teal |
| `--portal-paper` | `#FFFDF8` | readable card and workspace surface |
| `--portal-ink` | `#202124` | titles, active navigation, high-priority text |
| `--portal-muted` | `#68645D` | metadata and explanatory copy |
| `--portal-line` | `#D7D1C5` | quiet separators and control borders |
| `--portal-amber` | `#F4DF9C` | selected tabs, emphasis chips, gentle highlights |
| `--portal-amber-strong` | `#C67025` | the only warm primary action / map-marker color |
| `--portal-blue` | `#2F8CFF` | links, sync state, focus visible, concept references |
| `--portal-blue-soft` | `#E8F2FF` | linked-concept tag background |
| `--portal-danger` | `#B42318` | failures only |

Rules:

- The canvas may be warm, but long reading surfaces must stay `--portal-paper`.
- Amber never fills a whole Cloud page. It identifies selection, a call to action, or a geographic
  point; it never competes with content.
- Blue never identifies a Cloud. It means a live system link, keyboard focus, sync state, or a
  cross-Cloud knowledge relationship.
- No full-page teal, green, rainbow, glassmorphism, gradients, or synthetic dashboard washes.
- The Portal uses the Chinese-first system stack `PingFang TC`, `Noto Sans TC`, `Helvetica Neue`,
  `Arial`, sans-serif. It does not load a paid font.

## 3. Shell and responsive behavior

Desktop (at least 900 px) has a 208 px left rail. It contains Brain Cloud, Home, the available
Clouds, and Sources & Sync. The selected Cloud uses charcoal fill plus a 2 px amber inset or
keyline. The main area starts with a compact natural-language search field and source freshness.

At less than 900 px the rail becomes a horizontal, scrollable Cloud row. At less than 620 px the
utility destinations become a menu; every actionable element remains at least 44 px high. The
content is one column; sector cards become two columns, then one. Motion is only transform/opacity
at 160–180 ms and is disabled under `prefers-reduced-motion`.

All icons are local inline SVG, `20 × 20`, `stroke="currentColor"`, `stroke-width="1.75"`, round
caps and joins. The Portal must not use emoji, `◌`, `⌖`, `✦`, or ASCII glyphs as product icons.

## 4. Content hierarchy and cards

The shared rule is **purpose before fields**. A card shows the shortest useful answer, not a raw
database schema. Raw IDs, hash revisions, connector configuration, and internal routing keys never
appear in a user view.

### 4.1 Home

Home starts with one natural-language search: `搜尋：Web3 賽道、Ned Kelly、台北咖啡…`. Under it,
four quiet intent links are visible: `研究一個主題`, `找一個地點`, `重用一套方法`, `探索關聯`.

Cloud cards are a sparse grid, not a wall of database rows. Each card contains a semantic SVG icon
and public Cloud name; one-sentence purpose; two real, recent source-backed preview titles; item
count and freshness; and one arrow destination. Recent content is a compact reading queue. The
item type and Cloud are secondary metadata; the cleaned title is the primary scan target.

### 4.2 Web3 workspace

The visible order is eyebrow `11 · BUSINESS RESEARCH`, title `Web3 商業研究`, purpose, one primary
action `新增研究`, four tabs, sector map, latest research, then related concepts.

The sector map is a quiet three-column rule grid. A sector is rendered only if source-backed items
exist. A sector tile includes its name and its truthful count; clicking it searches that sector.
Research cards show type/date, cleaned title, a one- or two-line useful summary, and no more than
three cross-Cloud concept tags. A concept tag uses blue-soft because it is a navigable relation.

### 4.3 Food workspace

Food starts with the real map and a synchronized place list. The header reports actual coverage
(`N 可定位 / M 待補位置`). A marker or list-row selection synchronizes the other surface. A place
card is distinct from a research card: it shows category, area, visit status, name, and one next
action (`地圖導航` or `閱讀筆記`). A missing coordinate is honestly labelled `待補位置`; it is never
placed on a synthetic map.

### 4.4 Item and search results

An item has: breadcrumb/type, clean title, freshness, useful summary, takeaways, source body,
connected concepts, related items, and canonical source action. Search results reuse the content
type card and show a source-backed reason for the match. Search must not render a generic
`Knowledge Items` table as its primary result view.

## 5. Copy and public names

| Context | Web3 | Food | AI |
| --- | --- | --- | --- |
| rail / short label | Web3 | 美食地圖 | AI 自動化 |
| page heading | Web3 商業研究 | 美食與咖啡地圖 | AI 自動化 |

Use normalized public types: `研究報告`, `專案`, `概念`, `地點`, `工具`, `Agent`, `MCP`, `工作流`,
`教學`, `新聞`. The semantic icon is selected from the normalized public type/category, not from an
emoji inside a source filename.

## 6. Acceptance criteria

1. No Portal page uses the former green/teal palette or Unicode product glyph icons.
2. The page is visually calm: paper reading surfaces, one amber primary action per view, and blue
   only for system/relationship semantics.
3. Every page lets a first-time user answer: where am I, what can I do next, and what content is
   most relevant here.
4. Web3 shows real sector counts and research summaries; Food shows a real coordinate map and
   honest non-coordinate handling.
5. Search, Cloud cards, concepts, map markers, and list rows are keyboard reachable and keep a
   visible blue focus outline.
6. Portal links for canonical editing remain visibly labelled as source actions, so a Notion user
   can edit content without treating the Portal as an opaque data layer.
