# Brain Cloud Portal — Follow-up Backlog

Status at handoff: Brain Cloud Portal MVP (Tasks 1-7 of
`docs/superpowers/plans/2026-07-13-brain-cloud-portal-mvp.md`) is complete,
independently reviewed, and committed on `main` locally
(`261d41c..92bacdf`). Not deployed, not pushed. Obsidian and Notion remain
canonical; the Portal remains read-only.

Neither item below is in any task's approved file map. Both were identified
during Task 6/7 implementation and browser verification but deliberately
left out of scope to avoid expanding the approved plan. Recorded here so
they aren't lost, not because they are blocking.

## 1. `/sync` route shows a hardcoded status instead of real sync state

**Where**: `brain_portal/web.py`'s `sync()` route and
`brain_portal/templates/portal/sync.html`.

**Current behavior**: the route always renders
`{"state": "Up to date", "last_updated": ..., "source_count": ...}` —
`state` is a literal string, not derived from persisted sync history.

**Why it matters**: Task 6 added `PortalRepository.latest_sync()` and a real
Syncing/Up to date/Stale/Permission required badge on the *item* page. The
`/sync` overview page — the one place a user would go to check "is my whole
source healthy" — still doesn't use it. Design doc §"Manage Sources and Sync
Status" implies this page should show real freshness/failure state, and the
Task 7 plan's Step 6 browser story #5 ("simulated stale sync → visible
`Stale` status with last successful timestamp") is really about this page,
not just the item badge.

**Suggested fix**: call `dependencies.repository.latest_sync(tenant_id)`
(no `source_type` filter, or one call per distinct `source_type` present in
`_tenant_items()`) in the `sync()` route, map each `SyncRun.status` through
the existing `SYNC_STATUS_LABELS` in `web.py`, and pass the real
`finished_at` as `last_updated`. Needs a bounded-503 wrap like the item
route's `_sync_status_label()` if the lookup can fail. Write RED tests in
`tests/portal/test_web.py` first (a repository-failure-returns-503 case and
a real-vs-hardcoded-status case), per this project's established TDD
convention.

## 2. Notion connector/webhook are not wired into `portal_app.py` production dependency injection

**Where**: `brain_portal/connectors/notion.py`, `brain_portal/notion_webhook.py`
exist and are fully tested standalone (Task 6), but `portal_app.py`'s
`_default_dependencies()` and `create_app()` only construct
`PortalRepository`, `GeminiEmbeddingProvider`, `GeminiAnswerProvider`, and
`DeepSeekAnswerProvider` — no `NotionConnector`, no registration of the
`notion_webhook` blueprint.

**Why it matters**: without this wiring, a real deployment of `portal_app.py`
today cannot actually receive Notion `page.content_updated`/
`page.properties_updated` webhooks or serve a `NotionConnector`-backed
re-index — the guided-editing story from the design doc (§7.2) has no live
endpoint yet, even though every component it needs is built and tested.

**Suggested fix** (when authorized): add `notion_database_id` and
`notion_webhook_secret` to `PortalSettings` (`brain_portal/config.py`),
construct a `NotionConnector` in `_default_dependencies()` when
`notion_token`/`notion_database_id` are present, and register
`create_notion_webhook_blueprint(...)` on the Flask app in `create_app()`
alongside the portal blueprint. Add the corresponding names to
`.env.example` and `render.yaml`'s `brain-cloud-portal` service (some of
`NOTION_WEBHOOK_SECRET` is already there from Task 7; `NOTION_DATABASE_ID`
for the Portal's own tenant would still need adding — do not reuse the
existing LINE-capture `NOTION_DATABASE_ID` value, it's a different
database/workspace concern). This is real production wiring — do the usual
TDD pass, then treat enabling the live webhook URL as a deploy action
requiring explicit authorization, same as any other production change.

## Non-issues (already handled, listed so they aren't second-guessed later)

- Task 2's 500-character diagnostic truncation is implemented; its
  regression doesn't force an over-limit diagnostic (pre-existing debt,
  noted in the original handoff, still non-blocking).
- Python 3.9 / LibreSSL `NotOpenSSLWarning` from `urllib3` is environmental,
  not a Portal defect.
