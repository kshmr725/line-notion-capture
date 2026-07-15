# Brain Cloud Public Beta Production Plan

**Goal:** Ship the approved controlled Beta on a zero-cost-capable stack with real Notion OAuth, verified Notion event webhooks, durable tenant state, and an idempotent background queue.

**Architecture:** Keep SQLite as the local/test backend and add a PostgreSQL backend selected by `PORTAL_DATABASE_URL`. Production uses Supabase PostgreSQL for all portal state and projections; Render remains stateless. Notion webhooks enqueue only trusted workspace-resolved events. A scheduled, authenticated processor claims jobs with leases, retries transient failures, and dead-letters exhausted jobs.

**Safety boundaries:** Never log or commit credentials; never trust tenant IDs from webhooks; never write back to Notion or Obsidian; fail closed when production auth, OAuth, encryption, webhook, database, or processor credentials are missing; do not incur paid infrastructure.

## Task 1: Production database boundary

- Add RED tests for database URL selection and production fail-closed behavior.
- Add PostgreSQL schema/migration support while preserving SQLite tests.
- Add PostgreSQL lexical-search fallback that remains tenant scoped.
- Verify schema initialization is repeatable.

## Task 2: Durable webhook queue

- Add RED tests for duplicate delivery, concurrent claims, expired leases, bounded retries, and dead-letter state.
- Persist attempt count, availability, lease owner/expiry, and sanitized error code.
- Use an atomic backend-specific claim (`FOR UPDATE SKIP LOCKED` on PostgreSQL).
- Keep webhook response fast and tenant resolution server-side.

## Task 3: Production processor entrypoint

- Add a protected HTTP processor endpoint suitable for a zero-cost external scheduler.
- Require a constant-time bearer-token check and cap work per invocation.
- Retain the CLI processor for local recovery and operations.

## Task 4: OAuth/webhook/deployment contract

- Tighten OAuth configuration and callback validation for the public base URL.
- Verify Notion signatures against the raw body and document the one-time verification-token setup.
- Update Render configuration to use `PORTAL_DATABASE_URL` and production-only secrets.
- Add a GitHub Actions scheduled processor invocation without storing secrets in source.

## Task 5: Verification and release

- Extend `verify_go_live.py` to check durable database, HTTPS callback, webhook, processor, and fail-closed auth configuration without printing values.
- Run focused tests, full `pytest`, `git diff --check`, and a tracked-file secret scan.
- Commit locally in reviewable stages; do not push or deploy until the external credentials are available and the deployment checkpoint is recorded.
