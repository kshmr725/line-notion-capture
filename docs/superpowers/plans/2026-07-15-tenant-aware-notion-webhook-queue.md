# Tenant-Aware Notion Webhook Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept Notion change events safely for multiple tenants, deduplicate them, and process source updates outside the webhook request.

**Architecture:** The public endpoint verifies the Notion HMAC and uses the official `workspace_id` and unique event `id` to resolve an active tenant connection. It writes only a tenant-scoped, idempotent job to SQLite and responds immediately. A bounded worker claims one job, decrypts only that tenant's connection token, fetches the referenced page, invokes the existing `index_document`, and records completion or failure.

**Tech Stack:** Flask, SQLite, Python standard library, existing NotionConnector, AES-GCM token storage, pytest.

## Global Constraints

- Obsidian and Notion remain canonical; the portal only maintains a projection.
- Never trust a client-supplied tenant ID or persist raw webhook payloads/tokens.
- Webhook request handling performs no Notion fetch and no embedding call.
- Use the Notion event `id` for idempotency and `workspace_id` only to locate an active server-side connection.
- Keep the existing fixed-tenant webhook untouched until this replacement is verified.

---

### Task 1: Durable event and job records

**Files:**
- Modify: `brain_portal/db.py`
- Create: `brain_portal/notion_jobs.py`
- Test: `tests/portal/test_notion_jobs.py`

**Produces:** `enqueue_notion_event(repo, event) -> bool`, returning false for unknown workspaces or repeated event IDs.

- [ ] **Step 1: Write failing tests** that insert two active source connections, enqueue an event for one `workspace_id`, and assert exactly one job has that tenant; repeat the same event id and assert only one job remains.
- [ ] **Step 2: Run RED** with `pytest -q tests/portal/test_notion_jobs.py -k enqueue` and expect an import/attribute failure.
- [ ] **Step 3: Add `notion_webhook_events` and `notion_sync_jobs` tables** with `event_id` unique, tenant foreign keys, `queued|processing|completed|failed` status, source page id, and timestamps; persist only event metadata.
- [ ] **Step 4: Implement the enqueue function** by reading active Notion connection config JSON server-side, matching `workspace_id`, and atomically inserting the event plus job.
- [ ] **Step 5: Run GREEN and commit** `feat: queue tenant-aware notion webhook events`.

### Task 2: Signed webhook intake

**Files:**
- Create: `brain_portal/notion_event_webhook.py`
- Modify: `portal_app.py`, `brain_portal/config.py`, `render.yaml`
- Test: `tests/portal/test_notion_event_webhook.py`

**Consumes:** `enqueue_notion_event`; `NOTION_WEBHOOK_SECRET`.

**Produces:** `POST /hooks/notion/events`, returning 202 for valid recognized events without calling Notion.

- [ ] **Step 1: Write failing tests** for valid signed event queued under correct tenant, invalid signature rejected before JSON parsing, unknown workspace accepted without queueing, and duplicate event accepted without a second job.
- [ ] **Step 2: Run RED** with `pytest -q tests/portal/test_notion_event_webhook.py`.
- [ ] **Step 3: Implement the blueprint** using raw body HMAC validation, payload shape validation, `id`, `workspace_id`, and page `entity.id`; only signal event types are enqueued.
- [ ] **Step 4: Register only when a webhook secret exists** in `create_app`; no tenant override or API token is read from request input.
- [ ] **Step 5: Run GREEN and commit** `feat: accept tenant-aware notion webhook events`.

### Task 3: Bounded job processor

**Files:**
- Modify: `brain_portal/notion_jobs.py`
- Create: `scripts/process_notion_sync_jobs.py`
- Test: `tests/portal/test_notion_jobs.py`

**Consumes:** queued job, `decrypt_source_token`, `NotionConnector`, `index_document`.

**Produces:** `process_next_notion_job(settings, repo, embedder, connector_factory) -> str | None`.

- [ ] **Step 1: Write failing tests** for one claimed job fetching/indexing only the resolved tenant document, a denied fetch producing `permission_required`, and an empty queue returning `None`.
- [ ] **Step 2: Run RED** with `pytest -q tests/portal/test_notion_jobs.py -k process`.
- [ ] **Step 3: Implement atomic claim and completion/failure status updates**, decrypting connection config only after claim and passing the trusted tenant ID to `fetch_document` and `index_document`.
- [ ] **Step 4: Add a script** that processes at most one job and exits nonzero only for an unexpected processor crash; it prints job status, never tokens or payloads.
- [ ] **Step 5: Run GREEN and commit** `feat: process queued notion sync jobs`.

### Task 4: Verification and operator handoff

**Files:**
- Modify: `README.md`, `GO_LIVE.md`, `docs/handoffs/2026-07-15/controlled-beta-webhook-queue.md`
- Test: `tests/portal/test_security_e2e.py`

- [ ] **Step 1: Add a regression test** proving a valid event from one workspace cannot create or process a job for a second tenant.
- [ ] **Step 2: Run focused webhook/job/security tests**, then `pytest -q` and `git diff --check`.
- [ ] **Step 3: Document the external boundary**: configure the Notion subscription URL and schedule the processor only after production secrets and durable hosting are authorized.
- [ ] **Step 4: Commit docs and record a handoff checkpoint** with exact verifier output and the next external action.
