# Brain Cloud Controlled Beta and Insight Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Brain Cloud into a source-grounded, multi-user Second Brain with a free controlled-beta login/onboarding flow and regenerable table, chart, presentation, and briefing views.

**Architecture:** Obsidian remains Kevin's immutable canonical source; a general user's Notion workspace is canonical for that tenant. The Flask portal is a read-only projection over the indexed SQLite database. Insight views are derived artifacts identified by source IDs and query/configuration, so they can be regenerated after sync and never become a second source of truth.

**Tech Stack:** Existing Flask application, SQLite, Jinja templates, existing `PortalRepository`, hybrid search, citation-aware answer chain, Notion connector/webhook, Leaflet map, plain HTML/CSS/SVG/JSON. No paid service or new runtime dependency is required for the beta.

## Global Constraints

- Preserve the approved warm-paper/amber visual system in `docs/superpowers/specs/2026-07-14-brain-cloud-warm-portal-visual-system.md`; accidental green/teal palettes are prohibited.
- Keep `docs/superpowers/specs/2026-07-14-brain-cloud-zero-cost-beta.md` as the product baseline: magic-link login, Notion OAuth, per-tenant isolation, and a read-only portal.
- Every generated table/chart/slide/briefing must expose source links and source revision timestamps.
- Do not write back to Kevin's Obsidian vault; do not expose raw tenant IDs, coordinates, connector configuration, or provider prompts to end users.
- Use deterministic extraction first. LLM calls are optional enrichment and must degrade to a source-only result when unavailable.
- All protected routes require an authenticated tenant; cross-tenant reads and source IDs must be rejected.
- No push, deploy, OAuth provider registration, or schema migration against a live database without explicit principal authorization.

## Product boundary (must be implemented exactly)

Brain Cloud is not a NotebookLM clone. NotebookLM-style grounded synthesis is one capability inside a persistent knowledge operating layer that provides: canonical-source ownership, Cloud-specific navigation, cross-Cloud links, structured place/project/tool data, Notion/Obsidian synchronization, and user-editable source workflows. NotebookLM can be used as inspiration for briefing UX, but it is not the source of truth and its notebook model must not replace the Cloud model.

### Task 1: Controlled-beta authentication and tenant onboarding

**Files:**
- Create: `brain_portal/auth.py`
- Create: `brain_portal/templates/portal/login.html`
- Create: `brain_portal/templates/portal/onboarding.html`
- Modify: `brain_portal/db.py` (add `users`, `sessions`, `tenant_memberships`, `source_connections` onboarding fields)
- Modify: `brain_portal/models.py` (add `AuthenticatedPrincipal` and `OnboardingState`)
- Modify: `brain_portal/config.py` (magic-link/session settings and OAuth client settings)
- Modify: `portal_app.py` (register auth blueprint and authenticated tenant resolver)
- Modify: `brain_portal/web.py` (protect portal blueprint and add account/source entry points)
- Test: `tests/portal/test_auth.py`, `tests/portal/test_tenant.py`, `tests/portal/test_security_e2e.py`

**Interfaces:**
- `create_auth_blueprint(settings, repository) -> Blueprint` provides `GET /login`, `POST /login/request`, `GET /auth/verify`, `POST /logout`, and `GET /onboarding`.
- `resolve_authenticated_tenant() -> TenantContext | None` reads only a signed, expiring session and returns no tenant for anonymous requests.
- `begin_notion_oauth(principal_id: str) -> str` creates a state-bound authorization URL; `complete_notion_oauth(state: str, code: str) -> TenantContext` validates state before storing the per-tenant connection.

- [ ] **Step 1: Write failing tests** for anonymous redirect to `/login`, one-time magic-link verification, session expiry, tenant isolation, OAuth state mismatch, and onboarding state transitions (`needs_source → proposed → confirmed → indexing → ready`).
- [ ] **Step 2: Run** `pytest tests/portal/test_auth.py tests/portal/test_tenant.py tests/portal/test_security_e2e.py -q`; expected: the new tests fail because the routes and models do not exist.
- [ ] **Step 3: Implement** signed cookie sessions with an injectable clock/token signer for tests; store only hashed one-time tokens; use the existing `source_connections` table for a tenant-scoped Notion connection; keep OAuth secrets in environment variables.
- [ ] **Step 4: Run** the focused tests and then `pytest -q`; expected: all existing tests plus the new auth tests pass.
- [ ] **Step 5: Commit** `feat: add controlled beta authentication and notion onboarding`.

### Task 2: Cloud preview and source-backed onboarding

**Files:**
- Create: `brain_portal/onboarding.py`
- Modify: `brain_portal/connectors/notion.py`, `brain_portal/connectors/obsidian.py`
- Modify: `brain_portal/indexer.py`
- Modify: `brain_portal/templates/portal/onboarding.html`, `brain_portal/templates/portal/sync.html`
- Test: `tests/portal/test_onboarding.py`, `tests/portal/test_index_command.py`

**Interfaces:**
- `propose_clouds(documents: Sequence[SourceDocument]) -> tuple[CloudProposal, ...]` returns label, confidence, sample titles, and detected fields without mutating the source.
- `confirm_clouds(tenant_id: str, proposal_id: str, accepted: Mapping[str, str]) -> OnboardingState` records the user's choice and starts an explicit indexing run.

- [ ] **Step 1:** Add RED tests proving a proposal is deterministic for the same documents, low-confidence fields are shown as editable suggestions, and confirmation never writes to Obsidian/Notion.
- [ ] **Step 2:** Implement proposal generation from existing folder/cloud mappings, frontmatter, item type, concepts, and place metadata; fall back to the three approved Clouds (`web3`, `food`, `ai`) when no preference is supplied.
- [ ] **Step 3:** Add an onboarding preview with `接受並建立`, `修改分類`, and `稍後再做`; show a truthful source count and sync state.
- [ ] **Step 4:** Run focused tests, `python scripts/verify_brain_portal.py`, and the full suite.
- [ ] **Step 5:** Commit `feat: add source-backed cloud onboarding preview`.

### Task 3: Derived Views — tables first

**Files:**
- Create: `brain_portal/derived_views.py`
- Create: `brain_portal/templates/portal/view_builder.html`
- Create: `brain_portal/templates/portal/table_view.html`
- Modify: `brain_portal/web.py` (add `GET /views/new` and `GET /views/table`)
- Modify: `brain_portal/static/portal.css`, `brain_portal/static/portal.js`
- Test: `tests/portal/test_derived_views.py`, `tests/portal/test_web.py`

**Interfaces:**
- `build_table(items: Sequence[KnowledgeItem], columns: Sequence[str], filters: Mapping[str, str]) -> DerivedTable`.
- `source_refs_for_view(view: DerivedView) -> tuple[str, ...]` returns canonical source IDs in display order.
- `serialize_view(view: DerivedView) -> str` emits safe JSON for a shareable, reproducible view configuration.

- [ ] **Step 1:** Write RED tests for Web3 project tables (`sector`, `status`, `thesis`, `updated_at`), food tables (`name`, `rating`, `address`, `hours`, `price`, `features`), and AI tables (`kind`, `tool`, `workflow`, `reliability`). Assert source links are present and missing fields render `未提供`, never raw `None` or coordinates.
- [ ] **Step 2:** Implement deterministic field extraction from `KnowledgeItem`, `place`, concepts, and normalized reader text; do not call an LLM to build the table schema.
- [ ] **Step 3:** Add a consistent `轉成表格` entry to every Cloud view and a view builder that lets users choose columns, filters, and sort order without knowing database keys.
- [ ] **Step 4:** Run focused tests plus the accessibility suite; verify keyboard navigation and 44px targets.
- [ ] **Step 5:** Commit `feat: add source-linked derived table views`.

### Task 4: Charts, presentation mode, and grounded briefings

**Files:**
- Modify: `brain_portal/derived_views.py`, `brain_portal/answers.py`, `brain_portal/presentation.py`
- Create: `brain_portal/templates/portal/chart_view.html`
- Create: `brain_portal/templates/portal/briefing_view.html`
- Create: `brain_portal/templates/portal/slides_view.html`
- Modify: `brain_portal/web.py` (add `GET /views/chart`, `GET /views/slides`, `GET /views/briefing`)
- Modify: `brain_portal/static/portal.css`, `brain_portal/static/portal.js`
- Test: `tests/portal/test_derived_views.py`, `tests/portal/test_answers.py`, `tests/portal/test_web.py`

**Interfaces:**
- `build_chart(table: DerivedTable, chart_type: Literal["bar", "donut", "timeline"]) -> ChartSpec` emits labels, values, accessible text summary, and source IDs.
- `build_slides(view: DerivedView, title: str) -> tuple[SlideSpec, ...]` emits a source-linked HTML slide deck; no PowerPoint dependency is required for beta.
- `answer_query_with_citations(query: str, hits: Sequence[SearchHit], providers: Sequence[AnswerProvider]) -> CitedAnswer | None` reuses the existing Gemini→DeepSeek fallback and preserves source IDs.

- [ ] **Step 1:** Write RED tests for one Web3 sector chart, one food rating/price chart, one AI reliability chart, a mobile-readable slide deck, and a briefing that refuses to answer when no source supports the claim.
- [ ] **Step 2:** Implement charts with inline SVG and semantic text summaries; implement slides as print-friendly HTML with one claim cluster per slide and source links in the footer.
- [ ] **Step 3:** Implement NotebookLM-like briefing sections: `回答`, `關鍵證據`, `比較`, `未確定事項`, `來源`; every statement must map to one or more source IDs.
- [ ] **Step 4:** Add `匯出 CSV`, `複製 Markdown`, and browser print-to-PDF actions. Defer binary PPTX/XLSX generation until a separate authorized task.
- [ ] **Step 5:** Run the full suite, `git diff --check`, and manual browser verification for all three Clouds.
- [ ] **Step 6:** Commit `feat: add source-grounded charts slides and briefings`.

### Task 5: Zero-cost beta deployment and operator handoff

**Files:**
- Modify: `render.yaml`, `GO_LIVE.md`, `README.md`
- Create: `docs/handoffs/2026-07-14/controlled-beta-insight-studio.md`
- Test: `tests/portal/test_security_e2e.py`, `scripts/verify_go_live.py`

- [ ] **Step 1:** Document required environment names without values: session signing secret, magic-link delivery adapter, Notion OAuth client ID/secret, redirect URL, database path, Gemini key, and DeepSeek key.
- [ ] **Step 2:** Make the default deployment fail closed when auth configuration is absent; keep local development on a deterministic test login adapter only when `PORTAL_DEV_AUTH=true`.
- [ ] **Step 3:** Extend the go-live verifier to check anonymous redirect, tenant isolation, source links, stale-sync messaging, and provider fallback without printing secrets.
- [ ] **Step 4:** Run `pytest -q`, `python scripts/verify_go_live.py`, and `git diff --check`; record results in the handoff checkpoint.
- [ ] **Step 5:** Stop before deploy and request explicit authorization for OAuth app registration, Render environment changes, and public beta release.

## Self-review

- Product differentiation is explicit: persistent canonical source plus Cloud workflows, not a generic notebook chat clone.
- Auth, onboarding, tables, charts, slides, and briefings each have a bounded route/file/test surface.
- Derived outputs are reproducible and source-linked; no task makes the projection a second canonical store.
- Binary PPTX/XLSX generation and public deployment are intentionally outside this zero-cost beta plan and require a later authorization.
