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

External work still required before production:

1. Create/authorize the Notion public OAuth app and configure its callback.
2. Configure the Notion webhook subscription URL and secret.
3. Run the processor with durable scheduling; current SQLite queue is not durable across a free Render filesystem reset.
4. Add retry/lease recovery and migrate queue storage to the approved Supabase durable service before opening the beta.
