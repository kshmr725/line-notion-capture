# Brain Cloud Portal Design

Date: 2026-07-13

Status: Approved interaction design; awaiting written-spec review before implementation planning

## 1. Problem

The Notion-native Brain Cloud Pilot validated the data relationships but failed as a product surface.
Its homepage exposed database views, Cloud records opened as blank pages, Knowledge Items led with
metadata instead of answers, and retrieval required users to understand Notion database mechanics.
Even the system developer could not identify the intended path without explanation.

The product must make a personal knowledge system usable without teaching users its schema.

## 2. Product outcome

Build a read-only Cloud Portal that becomes the primary search, browse, and reading surface while
leaving canonical editing in each user's source system.

- Kevin's canonical source is the local Obsidian `Kevin_Brain` vault.
- A general user's canonical source is that user's Notion workspace.
- The Portal indexes source content but does not become a second editable truth source.
- Users search naturally, browse visually by Cloud, and open answer-first Knowledge Items.
- Every AI answer remains traceable to source-backed Knowledge Items.

## 3. Product principles

1. Search first, classification second.
2. Users see answers before metadata.
3. Cloud navigation is optional context, not a prerequisite for retrieval.
4. Every generated claim is traceable to an indexed Knowledge Item.
5. Portal data is a disposable projection; canonical content remains authoritative.
6. A source failure must be visible and isolated, never silently presented as fresh data.
7. Tenant isolation is a schema invariant, not a later feature.
8. General users edit a guided Notion page, not a raw database.

## 4. Approved experience direction

The visual reference is the Framer Directory template: editorial typography, curated cards, strong
spacing, restrained but identifiable Cloud color, and dynamic filtering. The product combines that
visual language with app-like directory filters and answer-first article pages.

The interface must avoid both extremes rejected during design review:

- no raw Notion-style master table as the primary view;
- no lifeless warm-gray dashboard with insufficient visual identity;
- no rainbow card system in which every function competes for attention.

Cloud colors may identify domains, but typography, spacing, and hierarchy perform most navigation.

## 5. Information architecture

### 5.1 Primary surfaces

1. Home
2. Search results
3. Cloud page
4. Knowledge Item
5. Concept page
6. Place detail and map
7. Manage Sources and Sync Status

The raw Clouds, Knowledge Items, Concepts, and Places datasets remain administration surfaces and
are never linked as the normal user journey.

### 5.2 Home

The home page uses four descending levels of emphasis:

1. A natural-language search field with example queries.
2. Optional intent shortcuts: Research a topic, Find a place, Reuse a method, Explore links.
3. A curated Cloud gallery.
4. Continue where you left off and recent content.

Utility links for Inbox, Recent, and Manage remain visually secondary.

### 5.3 Cloud page

A Cloud page narrows retrieval without becoming another folder listing. It contains:

- Cloud title and one-sentence purpose;
- search constrained to the Cloud;
- domain-specific filters;
- two to four curated Featured Paths;
- concise Knowledge Item cards;
- related Concepts and adjacent Clouds.

The shared shell remains consistent, while filters and featured paths change by domain:

- Web3: sector, project, thesis, market, status;
- Food: map, category, area, visit status, use case;
- AI Automation: tool, agent, MCP, workflow, reliability.

### 5.4 Knowledge Item

Knowledge Items are answer-first reading pages. The visible order is:

1. breadcrumbs and content type;
2. title, reading time, freshness, and confidence;
3. answer or meaningful summary;
4. key takeaways;
5. source-backed body or excerpt;
6. connected Concepts;
7. related Knowledge Items;
8. canonical source link and edit action.

Internal identifiers, sync hashes, tenant identifiers, routing rationale, and raw confidence fields
are hidden from normal readers.

## 6. Search and answer behavior

### 6.1 Query flow

1. Authenticate the user and resolve exactly one `tenant_id`.
2. Parse the query into text plus optional Cloud, type, Concept, place, and intent filters.
3. Run lexical and semantic retrieval within that tenant boundary.
4. Fuse and rerank candidates.
5. Generate an answer only from retrieved Knowledge Items.
6. Return the cited answer followed by traceable result cards.

### 6.2 Result presentation

The result page contains:

- the interpreted query and active filters;
- a concise AI answer;
- inline citations that open Knowledge Items;
- a result card grid or list;
- filter controls for Cloud, type, Concept, freshness, and place fields;
- an explicit no-answer state when evidence is weak.

### 6.3 Grounding rules

- The answer generator receives only tenant-scoped retrieved evidence.
- Every material claim must cite at least one Knowledge Item.
- If evidence is insufficient, the Portal says that it could not form a supported answer and still
  displays the closest source cards.
- Provider fallback may change the generator but cannot bypass citations or tenant filters.
- Existing Gemini-primary and DeepSeek-fallback behavior may be reused for generation after the
  retrieval boundary is enforced.

## 7. Canonical editing

### 7.1 Portal ownership

The Portal is read-only in the MVP. It never writes user-authored content directly to the index.

### 7.2 General user Notion flow

Each Knowledge Item exposes `Edit in Notion`. The link opens the canonical Notion page directly,
not the database view. The page uses a guided template with only these user-facing fields:

- title;
- summary;
- Cloud;
- Concepts;
- content body.

System identifiers, tenant identifiers, sync hashes, AI confidence, connector state, and index
timestamps are hidden. Notion changes enqueue re-indexing, and the Portal transitions from
`Syncing` to `Up to date` after successful ingestion.

New Notion content is created from the same guided template. Cloud management uses a separate,
simple Notion administration page rather than exposing item-level system fields.

### 7.3 Kevin Obsidian flow

Kevin's Knowledge Items expose `Open in Obsidian`. Kevin edits the canonical local note. The Notion
pilot remains a disposable projection and cannot overwrite the Obsidian source.

## 8. System architecture

### 8.1 Components

- Portal web application: home, Cloud, search, Knowledge Item, Concepts, Places, and sync status.
- Authentication and tenant resolver: produces the mandatory tenant context for every request.
- Obsidian source adapter: reads the registered canonical vault without mutation.
- Notion source adapter: reads canonical pages authorized for a tenant.
- Normalizer: maps source content into a stable shared schema.
- Policy layer: applies Cloud instructions and excludes disallowed or sensitive fields.
- Indexing worker: performs change detection, extraction, chunking, embedding, and index updates.
- Knowledge store: relational normalized records with mandatory tenant scoping.
- Search index: lexical and semantic retrieval over the same tenant-scoped records.
- Retrieval service: filter, fusion, rerank, and evidence packaging.
- Answer service: grounded answer generation with citation validation.
- Sync status service: freshness, failures, retries, and source-specific health.

The current Flask/Render LINE capture service remains independently deployable. Portal concerns are
not added to the existing monolithic `app.py`; integration occurs through explicit source and index
interfaces.

### 8.2 Normalized entities

Every stored entity includes `tenant_id`, a stable source identifier, canonical URL or path,
connector type, source revision, sync timestamp, and deletion state.

Primary entities are:

- Tenant
- Source Connection
- Cloud
- Knowledge Item
- Knowledge Chunk
- Concept
- Place
- Item-Cloud relation
- Item-Concept relation
- Item-Place relation
- Sync Run

The MVP uses a relational knowledge store with full-text and vector retrieval. A separate graph
database is not introduced; explicit relation tables satisfy current graph-navigation needs.

### 8.3 Change processing

1. Detect changed or removed source records.
2. Read only the changed records.
3. Apply source and Cloud-specific instructions.
4. Validate safety and required canonical pointers.
5. Upsert normalized entities and relations in one tenant-scoped transaction.
6. Replace affected search chunks and embeddings.
7. Mark the sync run successful and publish freshness.

Deleted source content is soft-deleted from the projection and excluded from retrieval. A failed run
does not delete the last successful projection.

## 9. Failure handling

- Source unavailable: retain the last successful projection and show `Last synced` plus `Stale`.
- Partial record failure: quarantine that record, continue the run, and surface the count to the owner.
- Indexing failure: keep the previous index revision active and retry with bounded backoff.
- Answer provider failure: use the configured provider fallback; if both fail, return source cards
  without an AI answer.
- Insufficient evidence: state that no supported answer is available.
- Unauthorized canonical link: hide the edit link and show a permission repair action.
- Tenant mismatch: reject before retrieval and record a security event without exposing data details.

## 10. Security and privacy

- Every application and database request receives tenant context from authenticated server state,
  never from an untrusted client field alone.
- Every retrieval query includes the resolved tenant boundary before ranking or answer generation.
- Connector credentials remain server-side and encrypted at rest.
- Secret files, environment data, contacts, financial evidence, and disallowed folders are excluded by
  source policy before indexing.
- Logs contain identifiers and counts, not note bodies, secrets, or generated evidence payloads.
- Canonical sources are read-only from the Portal worker.
- Cross-tenant tests must prove that shared titles, Concepts, and embeddings cannot leak results.

## 11. MVP scope

### Included

- Framer Directory-inspired home;
- search, intent shortcuts, and Cloud gallery;
- Web3, Food, and AI Cloud pages;
- hybrid lexical and semantic retrieval;
- cited AI answers and source result cards;
- answer-first Knowledge Item pages;
- Kevin's read-only Obsidian connector;
- one Notion test tenant with guided editing and re-indexing;
- tenant-scoped schema from the first migration;
- responsive desktop and mobile layouts;
- freshness and failure states.

### Excluded

- public signup and production multi-user OAuth;
- Portal-native editing;
- bidirectional Obsidian synchronization;
- full fourteen-Cloud migration;
- payments, team sharing, and granular collaboration permissions;
- graph database infrastructure;
- production deployment or migration during the design phase.

## 12. Verification and acceptance

### Product acceptance

- Reach a target Cloud within 10 seconds.
- Find a selected Web3 research item or restaurant within 30 seconds.
- Complete either task in at most three interactions.
- Achieve at least 80% correct routing within the top five results on the pilot query set.
- Attach Knowledge Item citations to 100% of generated material claims.
- Reflect a Notion test edit in the Portal within 60 seconds.
- Show a visible stale state when a source cannot refresh.
- Keep desktop and mobile navigation usable for the same core tasks.

### Security acceptance

- Zero cross-tenant results across API, retrieval, cache, and answer tests.
- No connector credential or note body in logs.
- No Portal write path to Kevin's Obsidian vault.
- No answer generation before tenant-scoped evidence retrieval.

### Reliability acceptance

- A failed incremental sync leaves the previous successful index readable.
- A failed answer provider returns source results instead of a broken page.
- Soft-deleted source records disappear from retrieval after the next successful sync.
- Reprocessing the same source revision is idempotent.

## 13. Implementation boundary

This document authorizes implementation planning only after explicit written-spec approval. It does
not authorize code changes, schema migrations, connector creation, deployment, purchasing the
Framer template, or external publication.
