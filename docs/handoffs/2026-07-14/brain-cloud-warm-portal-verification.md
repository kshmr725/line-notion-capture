# Brain Cloud warm Portal verification

Date: 2026-07-14  
Task: `2026-07-14-brain-cloud-zero-cost-beta`  
Canonical source: Obsidian vault (`/Users/kevinwu/Desktop/Kevin_Brain`)  
Mode: lexical-only, zero-cost local verification

## User-facing result

- Portal shell uses warm paper (`#F4F2ED` / `#FFFDF8`), charcoal, amber, and blue system links.
- Home starts with natural-language search, four intent links, Cloud cards, and a reading queue.
- Web3 uses source-backed concept/sector cards, recent research, and related concepts.
- Food uses validated source coordinates in a Leaflet/OpenStreetMap map when available, while the place list remains the no-JavaScript fallback.
- Food coverage after the canonical reindex: **26 places, 23 located, 3待補位置**.
- Cloud and item icons are local inline SVG; no product Unicode glyphs remain in the Cloud workspace.

## Commands and evidence

```text
.venv/bin/python scripts/index_brain_portal.py \
  --tenant kevin \
  --obsidian-root /Users/kevinwu/Desktop/Kevin_Brain \
  --database data/brain-portal.sqlite3 \
  --lexical-only
```

Result: `indexed: 44`, `unchanged: 0`, `deleted: 0`, `failed: 0`.

```text
.venv/bin/python scripts/verify_brain_portal.py \
  --database data/brain-portal.sqlite3 \
  --tenant kevin
```

Result: `valid: true`; no tenant leaks, missing canonical refs, unsafe canonical refs, stale syncs, or embedding-space conflicts.

Tests:

- `67 passed` for Portal web/accessibility contracts before map integration.
- `78 passed` for Portal web/accessibility/security contracts after map integration.
- `node --check brain_portal/static/portal.js` passed.
- `git diff --check` passed.

## Remaining operational boundary

The Leaflet/OpenStreetMap tiles are a free external runtime dependency. If a browser blocks the tile host or is offline, the accessible place list still exposes every source-backed location and canonical detail link. Notion OAuth onboarding and deployment remain controlled-beta operations; no external account mutation or paid service was performed here.
