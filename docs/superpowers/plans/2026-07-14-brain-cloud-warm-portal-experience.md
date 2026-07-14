# Brain Cloud Warm Portal Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the accidental green database-style Portal with the approved warm-paper Brain Cloud experience, using content-type cards, semantic icons, real Food map interaction, and truthful source-backed workspace data.

**Architecture:** Retain Flask/Jinja/SQLite and the normalized presentation layer. Add a template-only SVG icon system, source-backed Cloud previews/sector metadata, and Leaflet plus vanilla JavaScript only inside Food. The Portal stays read-only; canonical edits remain source links.

**Tech Stack:** Python 3, Flask, Jinja2, vanilla CSS/JavaScript, Leaflet 1.9.x from CDN, pytest.

## Global Constraints

- Use `#F4F2ED`, `#FFFDF8`, `#202124`, `#68645D`, `#D7D1C5`, `#F4DF9C`, `#C67025`, `#2F8CFF`, and `#E8F2FF` for approved roles; no green/teal tokens.
- Preserve canonical source files; normalize display data only in the Portal projection.
- Use local inline SVG icons; do not render `◌`, `⌖`, `✦`, emoji, or ASCII product icons.
- Every interactive control is at least 44 px and has a visible blue keyboard focus state.
- Map coordinates remain validated source facts. Do not invent positions or sector counts.
- No new paid service or runtime dependency is introduced.

---

## File structure

- `brain_portal/templates/portal/_icons.html`: Jinja macro rendering the fixed semantic SVG icon set.
- `brain_portal/presentation.py`: maps public type/category and Cloud key to a semantic icon name.
- `brain_portal/web.py`: creates source-backed Cloud preview cards, Web3 sector counts, and Food map payloads.
- `brain_portal/templates/portal/{base,home,cloud,search,item,place,sync,service_unavailable}.html`: warm shell and type-first pages.
- `brain_portal/static/portal.{css,js}`: responsive tokens and accessible map/list behavior.
- `tests/portal/{test_web,test_accessibility}.py`: rendered route, accessibility, and map contracts.

### Task 1: Define semantic SVG and presentation contracts

**Files:**
- Create: `brain_portal/templates/portal/_icons.html`
- Modify: `brain_portal/presentation.py`
- Modify: `brain_portal/web.py`
- Test: `tests/portal/test_web.py`

**Interfaces:**
- `icon_name_for_item(item: KnowledgeItem) -> str` returns a public icon name.
- `icon_name_for_cloud(cloud_key: str) -> str` returns `grid`, `orbit`, `map-pin`, or `workflow`.
- `_cloud_cards(items)` returns `icon_name`, `preview_titles`, `item_count`, and source-backed `freshness_label`.

- [ ] **Step 1: Write the failing route contract**

```python
def test_home_uses_semantic_svg_cloud_icons_and_real_previews(client):
    html = client.get("/").get_data(as_text=True)
    assert 'data-icon="orbit"' in html
    assert 'data-icon="map-pin"' in html
    assert "◌" not in html and "⌖" not in html and "✦" not in html
    assert "研究一個主題" in html
```

- [ ] **Step 2: Run it and verify failure**

Run: `pytest tests/portal/test_web.py::test_home_uses_semantic_svg_cloud_icons_and_real_previews -q`

Expected: FAIL because `CLOUDS` contains Unicode icons and Home has no intent copy.

- [ ] **Step 3: Implement the minimal public model**

Add `_icons.html` with `data-icon="{{ name }}"`, a `20 × 20` view box, `currentColor`,
and round caps/joins for the documented icon set. Add `icon_name_for_cloud()` and
`icon_name_for_item()` to `presentation.py`; use them in `web.py`. Make each Cloud card use
only clean source titles and its real count/newest timestamp.

- [ ] **Step 4: Verify and commit**

Run: `pytest tests/portal/test_web.py -q`

Expected: PASS.

```bash
git add brain_portal/presentation.py brain_portal/web.py brain_portal/templates/portal/_icons.html tests/portal/test_web.py
git commit -m "feat: add Brain Cloud semantic presentation"
```

### Task 2: Render the warm responsive shell and intent-first Home

**Files:**
- Modify: `brain_portal/templates/portal/{base,home,search,item,place,sync,service_unavailable}.html`
- Modify: `brain_portal/static/portal.css`
- Test: `tests/portal/test_web.py`
- Test: `tests/portal/test_accessibility.py`

**Interfaces:**
- Templates import `{% from "portal/_icons.html" import icon %}` and render `{{ icon(name) }}`.
- `main` has exactly one visible H1 per route.
- `.cloud-card`, `.knowledge-card`, `.intent-link`, and `.source-action` are shared classes.

- [ ] **Step 1: Write failing visual-semantic tests**

```python
def test_warm_token_contract_and_home_card_hierarchy(client):
    html = client.get("/").get_data(as_text=True)
    css = (ROOT / "brain_portal/static/portal.css").read_text().lower()
    assert "--portal-canvas: #f4f2ed" in css
    assert "--portal-amber-strong: #c67025" in css
    assert "--portal-blue: #2f8cff" in css
    assert "#2f7168" not in css
    assert 'class="intent-link"' in html
    assert 'class="cloud-card"' in html
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `pytest tests/portal/test_web.py tests/portal/test_accessibility.py -q`

Expected: FAIL because the stylesheet is green and Home renders generic rows.

- [ ] **Step 3: Implement the approved shell**

Replace the token declarations and shell layout. Use a 208 px rail at 900 px and above; below that
convert Cloud navigation to a horizontal scroller. Use paper for reading surfaces, amber only for
selected tabs/highlights/the primary action, and blue only for focus/source links/sync/concept tags.
Home renders search plus `研究一個主題`, `找一個地點`, `重用一套方法`, `探索關聯`, then sparse Cloud
cards and a compact reading queue. Every source action has a human name.

- [ ] **Step 4: Verify and commit**

Run: `pytest tests/portal/test_web.py tests/portal/test_accessibility.py tests/portal/test_security_e2e.py -q`

Expected: PASS.

```bash
git add brain_portal/templates/portal brain_portal/static/portal.css tests/portal/test_web.py tests/portal/test_accessibility.py
git commit -m "feat: render warm Brain Cloud portal shell"
```

### Task 3: Build truthful Web3 and Food workspaces

**Files:**
- Modify: `brain_portal/web.py`
- Modify: `brain_portal/templates/portal/cloud.html`
- Modify: `brain_portal/static/portal.css`
- Test: `tests/portal/test_web.py`

**Interfaces:**
- `_cloud_workspace(items, "web3", all_items)` returns actual `sectors`, each with `name`, `count`, and `url`.
- `_cloud_workspace(items, "food", all_items)` returns `map_points`, `coordinate_count`, `unlocated_count`, and public `places`.
- `#food-map[data-map-points]` exists only if a coordinate exists; unlocated places stay in `.place-list` with `待補位置`.

- [ ] **Step 1: Write failing workspace contracts**

```python
def test_web3_workspace_has_truthful_sector_cards_and_food_has_map_contract(client):
    web3 = client.get("/cloud/web3").get_data(as_text=True)
    food = client.get("/cloud/food").get_data(as_text=True)
    assert "賽道地圖" in web3
    assert 'class="sector-card"' in web3
    assert 'id="food-map"' in food
    assert 'data-map-points=' in food
    assert "待補位置" in food
```

- [ ] **Step 2: Run it and verify failure**

Run: `pytest tests/portal/test_web.py::test_web3_workspace_has_truthful_sector_cards_and_food_has_map_contract -q`

Expected: FAIL because the Web3 view uses generic filters and Food uses a CSS illustration.

- [ ] **Step 3: Implement source-backed workspace views**

Derive Web3 sectors from normalized item metadata/concepts; omit zero-count sectors; render eyebrow,
title, purpose, one action, tabs, sectors, latest research, and related concepts. For Food, use
Jinja `tojson` for raw validated point data and render category/area/status, clean title, and
named actions. Never use CSS percentage positions as geographic data.

- [ ] **Step 4: Verify and commit**

Run: `pytest tests/portal/test_web.py tests/portal/test_accessibility.py -q`

Expected: PASS.

```bash
git add brain_portal/web.py brain_portal/templates/portal/cloud.html brain_portal/static/portal.css tests/portal/test_web.py
git commit -m "feat: add purpose-first Cloud workspaces"
```

### Task 4: Add accessible Leaflet Food map synchronization and verify the vault

**Files:**
- Modify: `brain_portal/templates/portal/base.html`
- Modify: `brain_portal/static/portal.{css,js}`
- Modify: `tests/portal/test_web.py`
- Create: `docs/handoffs/2026-07-14/brain-cloud-warm-portal-verification.md`

**Interfaces:**
- `initFoodMap(element: HTMLElement): void` reads `data-map-points` and synchronizes marker/list selection.
- `brain-cloud:place-selected` has `detail: { sourceId: string }`.

- [ ] **Step 1: Write failing map contracts**

```python
def test_food_map_loads_leaflet_and_has_keyboard_selectable_place_rows(client):
    html = client.get("/cloud/food").get_data(as_text=True)
    js = (ROOT / "brain_portal/static/portal.js").read_text()
    assert "leaflet.css" in html
    assert "unpkg.com/leaflet@1.9.4" in html
    assert "initFoodMap" in js
    assert "brain-cloud:place-selected" in js
    assert 'data-place-source-id=' in html
```

- [ ] **Step 2: Run it and verify failure**

Run: `pytest tests/portal/test_web.py::test_food_map_loads_leaflet_and_has_keyboard_selectable_place_rows -q`

Expected: FAIL because Leaflet and synchronization are absent.

- [ ] **Step 3: Implement map/list behavior**

Load Leaflet CSS/JS only on Food. Parse only the JSON payload; construct marker popups from text,
add visible OSM attribution, and fit bounds. Marker click and place-row keyboard/click selection
toggle `.is-selected`, dispatch the named event, and focus the counterpart. Keep the place list as
the no-JavaScript fallback.

- [ ] **Step 4: Verify the source-backed result and commit**

Run:

```bash
pytest tests/portal/test_web.py tests/portal/test_accessibility.py -q
python scripts/index_brain_portal.py --tenant kevin --obsidian-root /Users/kevinwu/Desktop/Kevin_Brain --database data/brain-portal.sqlite3 --lexical-only
pytest -q
python scripts/verify_brain_portal.py --database data/brain-portal.sqlite3 --tenant kevin
git diff --check
```

Expected: tests PASS, verifier outputs `valid: true`, and diff check is silent. Record actual
coordinate/unlocated counts and commands in the verification handoff.

```bash
git add brain_portal/templates/portal/base.html brain_portal/static/portal.js brain_portal/static/portal.css tests/portal/test_web.py docs/handoffs/2026-07-14/brain-cloud-warm-portal-verification.md
git commit -m "feat: sync real Food map with place cards"
```

## Self-review

- Task 1 covers semantic icons and clean public presentation.
- Task 2 covers approved visual tokens, responsive behavior, navigation, and Home.
- Task 3 covers Cloud-specific Web3/Food card hierarchy without fabricated facts.
- Task 4 covers actual map behavior, keyboard fallback, and real-vault verification.
- This plan adds no paid service. Notion OAuth, authentication, and deployment stay in the separately approved controlled-beta architecture after this user-facing surface is stable.
