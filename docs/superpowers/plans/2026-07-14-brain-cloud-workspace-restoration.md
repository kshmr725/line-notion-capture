# Brain Cloud Workspace Restoration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the signed Cloud Shell as a functional, data-backed, Chinese-first Second Brain Portal, including a safe lexical-only ingestion path.

**Architecture:** Keep Flask, Jinja, SQLite and existing tenant-safe retrieval. Add small presentation models in `web.py`; templates render a shared Cloud workbench and domain-specific views. Indexing remains atomic; an explicit no-embedding mode writes ordinary FTS chunks only.

**Tech Stack:** Python 3, Flask, Jinja2, SQLite FTS5, vanilla CSS/JavaScript, pytest.

## Global Constraints

- Preserve `app.py` and all environment secrets.
- Portal is read-only; canonical actions only open validated Obsidian or Notion sources.
- Never use fake counts, freshness, locations, sectors, or AI previews.
- Keep tenant filtering, query limits, focus states, and 44px targets.
- Add no frontend framework or external runtime dependency.

## File structure

- `brain_portal/web.py`: Chinese Cloud definitions and data-derived view models.
- `brain_portal/templates/portal/base.html`: persistent responsive workspace shell and global search.
- `brain_portal/templates/portal/home.html`: Cloud tiles and recent list.
- `brain_portal/templates/portal/cloud.html`: domain-specific Web3, Food, and AI layouts.
- `brain_portal/templates/portal/{search,item,place,sync}.html`: existing semantics inside the shared shell.
- `brain_portal/static/portal.css`: visual tokens, layout, responsive behavior, compact cards.
- `brain_portal/indexer.py`, `scripts/index_brain_portal.py`: explicit lexical-only command path.
- `tests/portal/test_web.py`, `tests/portal/test_indexer.py`, `tests/portal/test_index_command.py`: evidence.

### Task 1: Build data-derived workspace models

**Files:** Modify `brain_portal/web.py`; test `tests/portal/test_web.py`.

**Produces:** Cloud cards `{key, name, description, icon, count, freshness, url}` and domain workspace structures derived only from `KnowledgeItem`.

- [ ] Write failing tests that assert the home carries `workspace-shell`, `我的 Cloud`, a real `2 筆` count, `尚未索引` for empty Clouds, and no former hero text.
- [ ] Run `pytest tests/portal/test_web.py -q`; confirm the old page fails.
- [ ] Implement `_cloud_cards(items)` and `_cloud_workspace(items, key)` in `web.py`; they compute counts and freshness from items, Web3 concept matrix counts, Food place list, AI type groups, and real search URLs.
- [ ] Run `pytest tests/portal/test_web.py -q`; commit `feat: derive Brain Cloud workspace data`.

### Task 2: Restore the signed shell and home

**Files:** Modify `base.html`, `home.html`, `portal.css`; test `tests/portal/test_web.py` and `tests/portal/test_accessibility.py`.

**Consumes:** Task 1 Cloud card fields and existing recent item cards.

- [ ] Write failing HTML assertions for `#cloud-rail`, `#global-search`, `#cloud-gallery`, `#recent-notes`, `continue-list`, and `data-cloud-key="web3"`.
- [ ] Run `pytest tests/portal/test_web.py -q`; confirm failure.
- [ ] Replace top-only navigation with `.workspace-shell` two-column layout, Chinese rail links, active state, and top global GET search. Replace hero/cards with compact real Cloud tile anchors and whole-row recent note anchors.
- [ ] Replace CSS with the signed 172px rail, calm neutral surfaces, teal accent, restrained per-Cloud tint, 2-column/1-column responsive collapse, and no timeline or decorative hero rules.
- [ ] Run `pytest tests/portal/test_web.py tests/portal/test_accessibility.py -q`; commit `feat: restore Cloud Shell home experience`.

### Task 3: Render three real Cloud workspaces and consistent reader views

**Files:** Modify `cloud.html`, `search.html`, `item.html`, `place.html`, `sync.html`, `portal.css`; test `tests/portal/test_web.py`.

**Consumes:** Task 1 workspace model.

- [ ] Write failing tests asserting Web3 `#sector-map`, a URL-backed tab query, Food `#food-discovery` list fallback, and Chinese canonical action labels.
- [ ] Run `pytest tests/portal/test_web.py -q`; confirm failure.
- [ ] Render Web3 concept/count matrix and latest items; Food map only if finite latitude/longitude, otherwise list-first place discovery; AI tool/agent/MCP/workflow/reliability filters. Tabs must be real `/search` links.
- [ ] Put search, item, place, sync inside shared workbench hierarchy while preserving their current safe IDs and canonical action validation.
- [ ] Run `pytest tests/portal/test_web.py tests/portal/test_accessibility.py tests/portal/test_security_e2e.py -q`; commit `feat: add Cloud-specific knowledge workspaces`.

### Task 4: Add explicit lexical-only ingestion

**Files:** Modify `indexer.py`, `scripts/index_brain_portal.py`; test `test_indexer.py`; create `test_index_command.py`.

**Produces:** `run_index(..., embedder=None)` writes chunks with NULL embeddings; CLI `--lexical-only` selects that behavior.

- [ ] Write failing tests that `run_index("kevin", connector, repo, None)` produces a lexical hit and that the CLI rejects a missing Gemini key without `--lexical-only` but succeeds with it.
- [ ] Run `pytest tests/portal/test_indexer.py tests/portal/test_index_command.py -q`; confirm failure.
- [ ] Make embedding-space validation, embedding calls, and persistence conditional on non-None embedder, preserving the existing transaction/soft-delete behavior. Add `--lexical-only`; output `"mode": "lexical-only"`; never silently fall back after an embedding failure.
- [ ] Run `pytest tests/portal/test_indexer.py tests/portal/test_search.py tests/portal/test_reliability_e2e.py -q`; commit `feat: support explicit lexical-only portal indexing`.

### Task 5: Index and prove real user journey

**Files:** Documentation only if the lexical command requires it.

- [ ] Run `.venv/bin/python scripts/index_brain_portal.py --tenant kevin --obsidian-root /Users/kevinwu/Desktop/Kevin_Brain --dry-run`; expect non-zero `would_index` and no source mutation.
- [ ] Run `.venv/bin/python scripts/index_brain_portal.py --tenant kevin --obsidian-root /Users/kevinwu/Desktop/Kevin_Brain --database data/brain-portal.sqlite3 --lexical-only`; expect mode lexical-only and failed zero.
- [ ] Run `.venv/bin/python -m pytest -q && .venv/bin/python scripts/verify_brain_portal.py --database data/brain-portal.sqlite3 --tenant kevin && git diff --check`; expect all PASS/valid/clean.
- [ ] Verify rendered hooks by `curl -fsS http://127.0.0.1:5050/ | rg 'workspace-shell|我的 Cloud|cloud-rail'`; do not bypass any localhost browser-control policy.
- [ ] Commit docs and evidence as `docs: record Brain Cloud workspace restoration`.

## Self-review

- Tasks 1-3 cover signed shell, real card contract, three Cloud workspaces, canonical actions, and mobile layout.
- Task 4 keeps the product usable while a provider key is unavailable without hiding degraded capability.
- Task 5 proves real vault ingestion, automated regression safety, and local delivery.
