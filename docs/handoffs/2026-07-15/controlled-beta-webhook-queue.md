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

Remaining product work: read `tenant_clouds` in the Portal shell so custom names become first-class homepage cards, navigation entries, search filters, and `/cloud/<custom-key>` pages. Until then the editor is safe and persists the decision, but the three canonical Cloud workspaces remain the only dedicated navigation views.

External work still required before production:

1. Create/authorize the Notion public OAuth app and configure its callback.
2. Configure the Notion webhook subscription URL and secret.
3. Run the processor with durable scheduling; current SQLite queue is not durable across a free Render filesystem reset.
4. Add retry/lease recovery and migrate queue storage to the approved Supabase durable service before opening the beta.
