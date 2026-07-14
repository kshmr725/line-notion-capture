# Brain Cloud Truthful UI and Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the signed black/white/blue Cloud experience while making Food maps, titles, type labels, and icons truthful projections of the existing Obsidian vault.

**Architecture:** Keep Flask/Jinja/SQLite. Add safe frontmatter projection, one semantic presentation module, raw coordinate map models, and an accessible Leaflet map with a no-JavaScript list fallback.

**Tech Stack:** Python 3, Flask, Jinja2, PyYAML safe loader, Leaflet, vanilla JavaScript/CSS, pytest.

## Global Constraints

- Use white `#FFFFFF`, ink `#1D2022`, line `#E5E5E5`, muted `#929292`, blue `#2F8DFF`, blue-soft `#E7F2FF`; no teal/green neutral tokens.
- Preserve canonical source files; normalize only the Portal projection.
- Use semantic inline SVG icons; do not render `◌`, `⌖`, or `✦`.
- Every target is 44px or larger; map/list selection works by keyboard.
- Validate `location: [lat, lng]`; reject non-finite/out-of-range coordinates.

---

### Task 1: Normalize Obsidian frontmatter and display semantics

**Files:**
- Create: `brain_portal/presentation.py`
- Modify: `brain_portal/connectors/obsidian.py`
- Modify: `brain_portal/indexer.py`
- Test: `tests/portal/test_obsidian_connector.py`
- Test: `tests/portal/test_indexer.py`

**Interfaces:**
- `parse_obsidian_metadata(body: str, filename_title: str) -> dict[str, object]`
- `clean_display_title(value: str) -> str`
- `public_item_type(metadata: dict[str, object]) -> str`

- [ ] **Step 1: Write failing tests**

```python
def test_food_frontmatter_exposes_valid_coordinates_and_clean_title(tmp_path):
    note = tmp_path / "71_Food_美食與咖啡地圖" / "2026-06-12 [咖啡店] Cozzi Café.md"
    note.parent.mkdir()
    note.write_text("---\nlocation: [25.033, 121.543]\n---\n# [咖啡店] Cozzi Café\n", encoding="utf-8")
    document = next(ObsidianConnector(tmp_path).iter_documents("kevin"))
    assert document.title == "Cozzi Café"
    assert document.metadata["place"]["latitude"] == 25.033
    assert document.metadata["place"]["category"] == "咖啡廳"
```

- [ ] **Step 2: Run it**

Run: `pytest tests/portal/test_obsidian_connector.py tests/portal/test_indexer.py -q`

Expected: FAIL because the connector omits YAML location and uses the filename stem.

- [ ] **Step 3: Implement minimal safe parsing**

```python
def _coordinates(value: object) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    latitude, longitude = (float(part) for part in value)
    return (latitude, longitude) if -90 <= latitude <= 90 and -180 <= longitude <= 180 else None
```

Use `yaml.safe_load`, an explicit field allowlist, title precedence YAML → H1 → filename, and a normalizer-version suffix in source revision.

- [ ] **Step 4: Verify and commit**

Run: `pytest tests/portal/test_obsidian_connector.py tests/portal/test_indexer.py -q`

Expected: PASS.

```bash
git add brain_portal/presentation.py brain_portal/connectors/obsidian.py brain_portal/indexer.py tests/portal/test_obsidian_connector.py tests/portal/test_indexer.py
git commit -m "feat: normalize Portal source semantics"
```

### Task 2: Expose truthful Cloud, title, type, and map models

**Files:**
- Modify: `brain_portal/web.py`
- Test: `tests/portal/test_web.py`

**Interfaces:**
- `_item_card(item)` returns `display_type`, `icon_name`, `cloud_label`, and a clean title.
- Food workspace returns raw `latitude`, `longitude`, `coordinate_count`, and `unlocated_count`.

- [ ] **Step 1: Write failing test**

```python
def test_food_workspace_exposes_real_lat_lng_and_unlocated_count(client):
    html = client.get("/cloud/food").get_data(as_text=True)
    assert 'data-latitude="25.033"' in html
    assert "25 可定位 / 1 待補位置" in html
```

- [ ] **Step 2: Run it**

Run: `pytest tests/portal/test_web.py -q`

Expected: FAIL because map points are synthetic percentages.

- [ ] **Step 3: Implement and verify**

Remove percentage normalization. Retain only validated coordinates, map raw keys to `Web3`/ `美食`/ `AI`, and derive semantic icon names by normalized type/category.

Run: `pytest tests/portal/test_web.py tests/portal/test_accessibility.py -q`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add brain_portal/web.py tests/portal/test_web.py
git commit -m "feat: expose truthful Cloud presentation models"
```

### Task 3: Restore the signed visual system

**Files:**
- Modify: `brain_portal/templates/portal/base.html`
- Modify: `brain_portal/templates/portal/{home,cloud,search,item,place,sync,service_unavailable}.html`
- Modify: `brain_portal/static/portal.css`
- Test: `tests/portal/test_web.py`
- Test: `tests/portal/test_accessibility.py`

- [ ] **Step 1: Write failing assertions**

```python
def test_shell_uses_signed_tokens_and_semantic_icons(client):
    html = client.get("/").get_data(as_text=True)
    css = (ROOT / "brain_portal/static/portal.css").read_text()
    assert 'data-icon="orbit"' in html
    assert 'data-icon="map-pin"' in html
    assert "#2F8DFF" in css and "#2f7168" not in css
    assert "研究一個主題" in html
```

- [ ] **Step 2: Run it**

Run: `pytest tests/portal/test_web.py tests/portal/test_accessibility.py -q`

Expected: FAIL due to Unicode icons, green palette, and missing intent shortcuts.

- [ ] **Step 3: Implement and verify**

Add an inline SVG macro. Restore desktop rail and narrow top navigation, black active pills with blue keyline, white editorial cards, Chinese public labels, intent shortcuts, and real Cloud preview titles.

Run: `pytest tests/portal/test_web.py tests/portal/test_accessibility.py tests/portal/test_security_e2e.py -q`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add brain_portal/templates brain_portal/static/portal.css tests/portal/test_web.py tests/portal/test_accessibility.py
git commit -m "feat: restore signed Brain Cloud visual system"
```

### Task 4: Render a real synchronized Food map

**Files:**
- Modify: `brain_portal/templates/portal/cloud.html`
- Modify: `brain_portal/static/portal.{css,js}`
- Test: `tests/portal/test_web.py`

**Interfaces:** `#food-map[data-map-points]` holds raw marker data; `initFoodMap(element)` creates markers and dispatches `brain-cloud:place-selected` with `sourceId`.

- [ ] **Step 1: Write failing test**

```python
def test_food_cloud_renders_leaflet_map_contract_when_coordinates_exist(client):
    html = client.get("/cloud/food").get_data(as_text=True)
    assert 'id="food-map"' in html
    assert 'data-map-points=' in html
    assert "leaflet.css" in html
```

- [ ] **Step 2: Run it**

Run: `pytest tests/portal/test_web.py -q`

Expected: FAIL because the current map is a CSS scatter illustration.

- [ ] **Step 3: Implement and verify**

Load Leaflet plus visible OSM attribution. Fit bounds over raw coordinates; click marker/list row toggles `.is-selected` and focuses its counterpart. Render every place without JavaScript and label non-coordinate places `待補位置`.

Run: `pytest tests/portal/test_web.py tests/portal/test_accessibility.py -q`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add brain_portal/templates/portal/cloud.html brain_portal/static/portal.css brain_portal/static/portal.js tests/portal/test_web.py
git commit -m "feat: render real Food map from source coordinates"
```

### Task 5: Verify the real vault

**Files:**
- Create: `docs/handoffs/2026-07-14/brain-cloud-truthful-ui-map.md`

- [ ] **Step 1: Index the vault**

Run: `python scripts/index_brain_portal.py --tenant kevin --obsidian-root /Users/kevinwu/Desktop/Kevin_Brain --database data/brain-portal.sqlite3 --lexical-only`

Expected: Food records index without failure and expose 25 valid coordinates plus one unlocated record.

- [ ] **Step 2: Run full verification**

Run: `pytest -q && python scripts/verify_brain_portal.py --database data/brain-portal.sqlite3 --tenant kevin && git diff --check`

Expected: PASS, valid, and no diff-check output.

- [ ] **Step 3: Commit evidence**

```bash
git add docs/handoffs/2026-07-14/brain-cloud-truthful-ui-map.md
git commit -m "docs: record truthful Portal map verification"
```

## Self-review

Tasks 1–2 are the isolated projection seam; Tasks 3–4 restore the signed UI and true map; Task 5 proves against Kevin's real vault. Notion OAuth, Supabase Auth, and deployment remain a separate plan so this portal can become usable before onboarding work is complete.

