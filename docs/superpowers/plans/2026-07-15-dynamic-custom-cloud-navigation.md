# Dynamic Custom Cloud Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make tenant-defined Cloud names first-class homepage cards, top navigation entries, search filters, and generic `/cloud/<custom-key>` workspaces.

**Architecture:** `PortalRepository.list_cloud_labels(tenant_id)` provides tenant-scoped metadata. `brain_portal.web` builds one request-local Cloud catalog by combining canonical definitions, persisted labels, and indexed item keys; every navigation surface consumes that same catalog. Canonical Web3/Food/AI pages retain their dedicated layouts, while custom keys use a generic source-backed workspace without unsupported derived-view links.

**Tech Stack:** Python, Flask/Jinja, SQLite, pytest.

## Global Constraints

- Never expose a Cloud label from another tenant.
- Never infer tenant identity from query parameters or route keys.
- Preserve the canonical Web3, Food, and AI dedicated workspaces.
- Custom Cloud pages show only indexed items assigned to that exact key.
- No write to Notion or Obsidian.
- Preserve the existing warm visual system and single-line desktop navigation.

---

### Task 1: Tenant Cloud metadata repository

**Files:**
- Modify: `brain_portal/db.py`
- Test: `tests/portal/test_db.py`

**Interfaces:**
- Produces: `PortalRepository.list_cloud_labels(tenant_id: str) -> dict[str, str]`

- [x] Write a failing test that inserts labels for two tenants and asserts only the requested tenant's ordered mapping is returned.
- [x] Run `.venv/bin/python -m pytest -q tests/portal/test_db.py -k cloud_labels` and confirm RED.
- [x] Implement one tenant-filtered query against `tenant_clouds`.
- [x] Run the focused test and commit `feat: expose tenant cloud labels`.

### Task 2: Request-local Cloud catalog and navigation surfaces

**Files:**
- Modify: `brain_portal/web.py`
- Modify: `tests/portal/test_web.py`

**Interfaces:**
- Consumes: `list_cloud_labels(tenant_id)` when available; fake/legacy repositories may omit it.
- Produces: `_cloud_catalog(dependencies, items)` definitions with `key`, `name`, `short_name`, `icon_name`, `description`, `filters`, `filter_labels`, `paths`, and `is_custom`.

- [x] Write failing tests proving a tenant custom Cloud appears on the homepage, top nav, search selector, and uses its persisted label on item cards.
- [x] Run the focused tests and confirm RED.
- [x] Build the catalog once per request from canonical definitions plus safe tenant metadata and indexed unknown keys.
- [x] Pass the catalog through context, home, search, item card, breadcrumbs, and filter summary helpers.
- [x] Run focused tests and commit `feat: surface custom clouds across navigation`.

### Task 3: Generic custom Cloud workspace

**Files:**
- Modify: `brain_portal/web.py`
- Modify: `brain_portal/templates/portal/cloud.html`
- Modify: `brain_portal/static/portal.css`
- Test: `tests/portal/test_web.py`, `tests/portal/test_accessibility.py`

**Interfaces:**
- Consumes: request-local Cloud definition where `is_custom == True`.
- Produces: `/cloud/<custom-key>` with exact-key item isolation, recent content, concepts, adjacent Clouds, and search action.

- [x] Write failing tests for a 200 custom page, exact-key item isolation, accessible shell, and 404 for unknown/unowned keys.
- [x] Run focused tests and confirm RED.
- [x] Allow only catalog-owned route keys and render a generic custom layout.
- [x] Hide table/chart/slides/briefing links for custom keys until derived-view schemas exist.
- [x] Run focused and accessibility tests; commit `feat: add custom cloud workspace`.

### Task 4: Verification and handoff

**Files:**
- Modify: `README.md`
- Modify: `docs/handoffs/2026-07-15/controlled-beta-webhook-queue.md`

- [x] Document dynamic custom Cloud behavior and the projection-only boundary.
- [x] Run `.venv/bin/python -m pytest -q` and `git diff --check`.
- [x] Browser-verify home, custom Cloud, search filter, and responsive navigation.
- [ ] Record a handoff checkpoint with remaining external deployment blockers.
