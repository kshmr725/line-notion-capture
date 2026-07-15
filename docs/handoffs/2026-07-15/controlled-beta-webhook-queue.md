# Controlled Beta Notion Webhook Queue

Implemented locally on `main`:

- `6cc12d6`: durable tenant-aware Notion event/job tables and idempotent enqueue.
- `bfa13df`: signed `POST /hooks/notion/events` intake, registered only with `NOTION_WEBHOOK_SECRET`.
- `650ddd8`: one-job processor command, `python scripts/process_notion_sync_jobs.py`.

Security contract:

- The request body never chooses a tenant. The intake maps official Notion `workspace_id` to an active server-side source connection.
- Event `id` is unique and can only create one queue entry.
- The handler only verifies and enqueues; it performs no Notion fetch, decryption, or embedding request.
- The processor claims one queued job, decrypts only its tenant connection, and sends the trusted tenant ID to the existing connector/indexer.

Verification: `387 passed`, focused webhook/job suite passes, `git diff --check` clean, and the processor command returns `idle` on an empty initialized database.

## Editable Cloud proposal continuation

Local `main` now also includes the user-decision layer before first indexing:

- `4f149c1`: pure source-level Cloud proposal revision model.
- `32c56f1`: tenant-scoped confirmation, exclusions, and persisted custom labels.
- `e0c0647`: accessible per-source Cloud-name editor and exclusion controls.

The user edits only the Portal projection. The flow never writes, moves, or deletes Notion/Obsidian source content. Submitted source IDs are accepted only when they belong to the authenticated tenant's stored proposal. Matching Cloud names merge; new names split into deterministic custom keys; excluded sources are omitted from the projection.

Verification after this continuation: `391 passed` and `git diff --check` clean.

Dynamic custom Cloud navigation is now implemented locally:

- `e9dae7d`: tenant-scoped Cloud label repository.
- `3459698`: one request-local catalog shared by homepage, top navigation, search, item labels, breadcrumbs, and filter summaries.
- `2dab8a4`: generic exact-key `/cloud/<custom-key>` workspace with unsupported derived-view actions hidden.
- `1221b88`: responsive search and long-row safeguards found during browser verification.

Canonical Web3/Food/AI workspaces retain their domain-specific layouts. Custom labels never cross tenants, and unknown/unowned route keys return 404. The external OAuth/webhook/durable-worker deployment blockers below remain unchanged.

External work still required before production:

1. Create/authorize the Notion public OAuth app and configure its callback.
2. Configure the Notion webhook subscription URL and secret.
3. Run the processor with durable scheduling; current SQLite queue is not durable across a free Render filesystem reset.
4. Add retry/lease recovery and migrate queue storage to the approved Supabase durable service before opening the beta.
