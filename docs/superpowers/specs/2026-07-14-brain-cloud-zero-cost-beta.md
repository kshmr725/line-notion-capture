# Brain Cloud Zero-Cost Controlled Beta

Date: 2026-07-14

Status: Approved product direction; written specification for implementation review

Task: `2026-07-14-brain-cloud-zero-cost-beta`

## 1. Outcome

Deliver a controlled-beta Second Brain that a general user can start without understanding the
underlying schema:

1. sign in through an email magic link;
2. authorize a Notion workspace through OAuth;
3. select existing pages or duplicate a guided Second Brain template;
4. review an automatically proposed Cloud structure;
5. confirm the structure and wait for source-backed indexing;
6. search, browse, read, map, and follow cross-Cloud Wiki links in Brain Cloud Portal;
7. edit canonical content in Notion and see the projection refresh.

Kevin remains a special source profile: his Obsidian vault is canonical and the Portal must never
write to it. For general users, Notion is canonical. The Portal is a read-only projection and may be
rebuilt from the source.

Development and closed testing must have zero mandatory infrastructure cost. Paid capacity is an
operational upgrade, not an architectural rewrite.

## 2. Signed visual source

The visual source of truth is the user-provided 2026-07-14 screenshot of the earlier Cloud Shell,
not the green restoration currently in `brain_portal/static/portal.css`.

The approved shell has these non-negotiable traits:

- a white canvas and near-black typography;
- one vivid blue interaction color;
- black active navigation and primary actions;
- a visible blue selection/focus keyline;
- thin neutral-gray dividers;
- editorial spacing instead of tinted dashboard panels;
- clear line icons;
- a desktop left navigation rail;
- a compact horizontal navigation row at narrow widths;
- Cloud cards and navigation that open domain-specific workspaces;
- cross-Cloud Wiki relationships visible near the content, not hidden in metadata.

The July 10 Cloud Shell HTML remains a structural reference only. Its semantic host variables did
not define a palette. The later green palette was invented during restoration and is explicitly
rejected.

### 2.1 Visual tokens

Implementation uses a restrained token system based on the signed screenshot:

| Token | Value | Use |
| --- | --- | --- |
| `canvas` | `#FFFFFF` | page background |
| `surface` | `#FFFFFF` | cards and controls |
| `ink` | `#1D2022` | primary text and active controls |
| `muted` | `#929292` | timestamps, counts, secondary labels |
| `line` | `#E5E5E5` | borders and list separators |
| `blue` | `#2F8DFF` | links, keylines, active matrix rules |
| `blue-soft` | `#E7F2FF` | concept chips and subtle selection |
| `danger` | `#B42318` | errors only |
| `warning` | `#9A6700` | stale and incomplete data only |

Cloud identity must come from icon, label, and content structure. Full-page green, teal, or rainbow
Cloud washes are prohibited.

### 2.2 Typography and spacing

- Chinese-first system stack: `PingFang TC`, `Noto Sans TC`, `Helvetica Neue`, sans-serif.
- Display: 32–40 px, weight 700, tight but readable leading.
- Section title: 18–22 px, weight 650–700.
- Card and row title: 16 px, weight 600–650.
- Body: 14–16 px, 1.55 line height.
- Metadata: 12–14 px, muted, tabular numerals for counts and dates.
- Minimum interactive target: 44 by 44 px on every viewport.
- Motion: 160–180 ms opacity/transform only; respect reduced motion.

## 3. Information architecture

### 3.1 Shared shell

Desktop navigation order:

1. Brain Cloud brand;
2. Home;
3. Web3;
4. Food Map;
5. AI Automation;
6. Sources and Sync;
7. Account.

At widths below 620 px, the primary Cloud navigation becomes the horizontal row shown in the signed
screenshot. Utility destinations move into a compact menu. The active destination uses near-black
fill, white label and icon, and a vivid-blue keyline.

### 3.2 Home

The home hierarchy is:

1. a large natural-language search field with real examples;
2. quiet intent shortcuts: `研究一個主題`, `找一個地點`, `重用一套方法`, `探索關聯`;
3. Cloud cards ranked by recent usage;
4. recent and continue-reading content;
5. a pending Cloud preview when automatic classification needs confirmation.

Cloud cards expose the full Cloud name, purpose, two real preview titles, item count, freshness, and
an arrow. They do not expose raw database keys or generic placeholder copy.

### 3.3 Web3 workspace

The approved signed view is restored:

- eyebrow `11 · BUSINESS RESEARCH`;
- title `Web3 商業研究`;
- concise purpose statement;
- `新增研究` canonical action;
- tabs `賽道總覽`, `專案庫`, `研究報告`, `概念 Wiki`;
- sector map built from real concepts and counts;
- latest research list;
- related concepts that search across all Clouds.

The sector map must never display fabricated counts. Empty sectors are omitted or shown as an
explicit suggestion.

### 3.4 Food workspace

The default Food view is a real interactive map synchronized with a place list.

- map markers use valid stored coordinates;
- the map fits all valid markers and clusters overlapping points;
- selecting a marker highlights the matching list row and opens an accessible summary;
- selecting a list row focuses the matching marker;
- a place without coordinates remains in the list with `待補位置`;
- the header displays truthful coverage, initially `25 可定位 / 1 待補位置` for Kevin's vault;
- actions are `地圖導航` and `閱讀筆記`;
- map attribution remains visible.

Development uses Leaflet with OpenStreetMap development tiles behind a provider interface. A
commercial provider can replace the tile URL and attribution through configuration without changing
the map model or templates.

### 3.5 AI Automation workspace

The workspace groups real content by normalized type:

- Tool;
- Agent;
- MCP;
- Workflow;
- Guide;
- Reliability note.

It emphasizes reusable methods and connected concepts rather than a flat list of everything marked
`research`.

### 3.6 Knowledge Item

Visible order:

1. breadcrumbs and normalized content type;
2. cleaned display title;
3. freshness and reading time;
4. useful summary or cited answer;
5. takeaways;
6. source-backed body;
7. connected concepts and related items;
8. canonical edit/open action.

Raw tenant IDs, source hashes, connector configuration, routing explanations, and internal item-type
keys remain hidden.

## 4. Naming and semantic normalization

Canonical filenames and source pages are not renamed. The projection derives a clean display model.

### 4.1 Display-title precedence

1. non-empty YAML `title`;
2. first valid H1;
3. filename stem.

The chosen display title then removes:

- a leading `YYYY-MM-DD` import date;
- decorative leading emoji;
- a leading bracketed category such as `[咖啡廳]`;
- duplicated date or category text;
- accidental repeated whitespace.

Date and category are preserved as separate structured fields.

### 4.2 Public naming contract

| Context | Web3 | Food | AI |
| --- | --- | --- | --- |
| Navigation/badge | Web3 | 美食 | AI |
| Page/card | Web3 商業研究 | 美食與咖啡地圖 | AI 自動化 |

Public item types use consistent labels:

`研究報告`, `專案`, `概念`, `地點`, `工具`, `Agent`, `MCP`, `工作流`, `教學`, `新聞`.

Food aliases normalize as follows:

- `咖啡店`, `黑膠咖啡` → `咖啡廳`;
- `甜點店` → `甜點`;
- mixed categories such as `咖啡廳／酒吧` remain multi-label values;
- `餐廳景點` becomes primary `餐廳` plus secondary `景點`.

### 4.3 Icon contract

Icons are local inline SVG symbols with a 20 px view box, 1.75 px stroke, round caps/joins, and
`currentColor`. Unicode symbols such as `◌`, `⌖`, and `✦` are removed.

Required semantic icons:

- Home: grid;
- Web3: orbit/nodes;
- Food: map pin;
- AI: workflow;
- report: file text;
- project: layers/cube;
- concept: connected nodes;
- restaurant: fork and knife;
- cafe: coffee;
- bar: glass;
- dessert: cake;
- tool: wrench;
- Agent: robot;
- MCP: plug;
- workflow: branch;
- guide: book;
- news: newspaper.

## 5. Source ingestion and map repair

### 5.1 Safe Obsidian frontmatter subset

The Obsidian connector parses only an allowlisted YAML subset:

- `title`;
- `date`;
- `type`;
- `tags`;
- `location`;
- `latitude`;
- `longitude`;
- `address`;
- `area`;
- `category`;
- `status`;
- `summary_brief`;
- `source`.

`location: [lat, lng]` is preferred, with separate latitude/longitude fields accepted as fallback.
Latitude must be finite and between -90 and 90. Longitude must be finite and between -180 and 180.
Invalid values never become markers and are surfaced as a record warning.

No general-purpose YAML object construction is allowed. Parsing must use safe loading plus type and
size bounds.

### 5.2 Source revision behavior

Normalizer behavior is versioned. A normalization-version change must force reprocessing even when
the source bytes are unchanged. This is required so existing Food records gain coordinates after the
connector fix.

Lexical-only indexing explicitly removes or ignores incompatible retained embeddings and reports the
active search mode truthfully.

## 6. Controlled-beta onboarding

### 6.1 Account flow

1. An invited user enters an email address.
2. Supabase sends a magic link through configured SMTP.
3. The callback establishes a secure server session.
4. The user lands on a checklist, not an empty Portal.

The app account is independent from Notion so the same identity can later connect Obsidian, Google
Drive, or multiple Notion workspaces.

### 6.2 Notion OAuth

- use a Notion public connection with installation scope `Any workspace`;
- gate application access with the controlled-beta invite list;
- validate OAuth `state` and bind it to the authenticated session;
- exchange the authorization code server-side;
- store workspace identity and encrypted access token per source connection;
- never expose the token to the browser or logs;
- support reconnect and disconnect;
- use the `2026-03-11` API and `/data_sources/{data_source_id}/query`;
- retrieve the database container and data-source IDs separately;
- handle token revocation as a visible `需要重新連接` state.

### 6.3 Template and source selection

After OAuth, the user chooses one of two paths:

1. duplicate the guided Brain Cloud Notion template; or
2. select an existing authorized database/data source.

The guided template exposes only understandable fields:

- Name;
- Summary;
- Cloud;
- Type;
- Concepts;
- Address;
- Location;
- Status;
- body.

System IDs, tenant IDs, sync state, hashes, tokens, and confidence values remain hidden.

### 6.4 Cloud preview and approval

The system samples source titles, types, tags, and summaries, then proposes:

- Cloud names;
- which items belong to each Cloud;
- suggested item types;
- unmapped or ambiguous items.

The user can rename, merge, split, move, or exclude before confirmation. No proposed taxonomy becomes
canonical without explicit user approval.

Gemini may improve suggestions when a free quota or user-provided key is available. A deterministic
rule-based preview remains available when AI is unavailable. The interface calls this `自動建議`
unless an AI provider actually produced it.

## 7. Zero-cost development architecture

### 7.1 Services

- Render Free Web Service: Flask Portal and OAuth callback;
- Supabase Free Auth: magic-link identity;
- Supabase Free Postgres: tenant data and durable job/event records;
- Supabase Edge Function: fast Notion webhook intake;
- Supabase Cron: reconciliation and stalled-job wake-up;
- Resend Free SMTP: controlled-beta authentication mail;
- Leaflet plus development map tiles;
- Gemini free quota or deterministic fallback;
- optional user-provided DeepSeek key, disabled by default for platform-funded calls.

### 7.2 Expected free-tier degradation

- Render may sleep after 15 idle minutes; the next web request may cold-start for about one minute.
- Supabase may pause after one week without activity.
- no infrastructure SLA is claimed;
- the projection database has no managed backup on the free plan;
- Notion remains canonical, so projection records are rebuildable;
- auth and connection loss require users to reconnect;
- sync target is one to ten minutes, not real time;
- the closed test is limited to approximately 10–20 invited users;
- public production launch is not authorized on free infrastructure.

The UI must disclose `首次載入可能需要約一分鐘` and show exact sync state rather than a spinner with
no explanation.

### 7.3 Upgrade seam

Configuration selects replaceable implementations for:

- database repository;
- job executor;
- mail transport;
- map tile provider;
- answer provider;
- embedding provider.

Moving to paid Render compute, a continuous worker, Supabase Pro, or commercial map tiles must not
change the public data model or onboarding flow.

## 8. Multi-tenant data model

Primary tables:

- `users`;
- `tenants`;
- `memberships`;
- `beta_invites`;
- `source_connections`;
- `oauth_states`;
- `clouds`;
- `knowledge_items`;
- `knowledge_chunks`;
- `concepts`;
- `item_concepts`;
- `places`;
- `sync_runs`;
- `sync_jobs`;
- `webhook_events`.

Every user-visible data table carries `tenant_id`. Database policies and repository methods both
enforce tenant boundaries. Client-supplied tenant IDs never determine server authority.

OAuth tokens are encrypted at application level with authenticated encryption and a versioned key
identifier. Ciphertext, nonce, and key version are stored separately. Secret keys remain in service
configuration and support rotation.

## 9. Sync lifecycle

1. OAuth or a webhook creates a tenant-scoped durable event/job.
2. Webhook intake verifies the initial Notion verification token or subsequent request signature.
3. The intake endpoint returns quickly without fetching page content or generating embeddings.
4. A processor claims a bounded batch using an atomic lease.
5. It applies per-connection rate limiting and honors Notion `429 Retry-After`.
6. It reads, normalizes, and validates only authorized records.
7. It commits the projection and relations transactionally.
8. It records success, partial failure, permission repair, or retry state.
9. Periodic reconciliation discovers missed updates and deletions.

Jobs are idempotent. Duplicate events do not duplicate knowledge items. A failed update leaves the
last successful projection readable.

## 10. Failure states and user copy

Required states:

- `準備中`: account exists but no source is connected;
- `等待授權`: Notion OAuth not completed;
- `正在建立你的 Brain Cloud`: initial sync in progress with counts;
- `已是最新`: latest successful source revision indexed;
- `部分內容需要處理`: some records quarantined, projection still usable;
- `需要重新連接`: token revoked or permission removed;
- `需要更新`: reconciliation or indexing stale;
- `搜尋已降級`: semantic/AI provider unavailable, lexical retrieval active;
- `待補位置`: a place lacks valid coordinates.

No page may report `Up to date` without repository evidence.

## 11. Security boundary

- invite-only signup for the controlled beta;
- secure, HTTP-only, same-site session cookies;
- CSRF protection for state-changing requests;
- OAuth `state` is one-time, expiring, and session-bound;
- tenant resolution comes from authenticated server state;
- RLS plus repository tenant filters;
- secrets and canonical content are excluded from logs;
- no webhook payload tenant is trusted;
- webhook events have replay protection and bounded body sizes;
- source connectors are read-only;
- no Portal write path to Kevin's Obsidian vault;
- no generated answer without tenant-scoped cited evidence;
- disconnect revokes or deletes stored credentials and stops sync;
- account deletion removes projections and credentials while leaving canonical Notion content.

## 12. Delivery phases

### Phase A — product truth restoration

- restore the signed black/white/blue shell;
- replace Unicode icons with the semantic SVG system;
- normalize display titles, types, and public labels;
- parse Obsidian frontmatter safely;
- re-index existing records and display 25 mapped places;
- implement the real synchronized Food map;
- restore search/intent shortcuts and cross-Cloud concepts;
- verify desktop and mobile behavior.

### Phase B — portable multi-tenant foundation

- add Postgres-compatible migrations and repository boundaries;
- add users, tenants, memberships, source connections, jobs, and webhook events;
- preserve SQLite only as a local-test adapter;
- add Supabase session validation and invite gating;
- add encrypted connection credential storage.

### Phase C — Notion controlled-beta onboarding

- implement public OAuth and reconnect/disconnect;
- migrate the connector to the data-source API;
- add template/data-source selection;
- add Cloud preview, adjustment, and confirmation;
- connect initial sync, webhook intake, and reconciliation;
- expose truthful onboarding and source-status UI.

### Phase D — zero-cost deployment and verification

- configure Render Free Web Service;
- configure Supabase Free Auth/Postgres/Cron/Edge Function;
- configure Resend Free SMTP;
- configure Notion redirect and webhook URLs;
- run one Kevin/Obsidian and one general-user/Notion end-to-end story;
- publish only to the invite-gated controlled-beta URL;
- record upgrade triggers and rollback steps.

## 13. Verification

### 13.1 Product acceptance

- the Portal matches the signed screenshot's black/white/blue hierarchy;
- no green or teal neutral token remains;
- Cloud navigation works from the rail and home cards;
- Web3, Food, and AI expose distinct useful workspaces;
- Kevin's vault reports 26 places, 25 mapped, and one awaiting location;
- a mapped place can be selected from map and list in both directions;
- display titles contain no import-date or leading-category noise;
- semantic icons match item type and category;
- related concepts search across Clouds;
- all touch targets are at least 44 px;
- desktop and mobile screenshots pass visual comparison review.

### 13.2 Onboarding acceptance

- only invited users can create an account;
- a magic link establishes the correct authenticated identity;
- OAuth rejects invalid, reused, expired, or cross-session state;
- the user can duplicate a template or select an authorized data source;
- Cloud suggestions do not activate before user confirmation;
- initial sync resumes after interruption;
- a revoked Notion token produces `需要重新連接`;
- a Notion edit appears within the free-tier one-to-ten-minute target;
- disconnect stops sync and removes credential access.

### 13.3 Reliability and security acceptance

- zero cross-tenant reads across UI, search, sync, cache, and answers;
- duplicate webhooks are idempotent;
- Notion `429` responses are retried with `Retry-After`;
- a failed record does not roll back unrelated valid records;
- a failed sync leaves the last successful projection readable;
- AI failure returns lexical results and truthful degraded state;
- no secret, token, note body, or database row is printed to logs;
- free-service cold start and paused-project states have actionable copy;
- full test suite, focused security tests, accessibility checks, and deployment smoke tests pass.

## 14. Explicit exclusions

- public unrestricted signup;
- payments and subscriptions;
- enterprise SSO;
- organization/team administration;
- Portal-native content editing;
- bidirectional writes to Obsidian;
- guaranteed real-time sync;
- production SLA;
- paid infrastructure purchase;
- public Marketplace listing;
- automatic migration of all fourteen Kevin Brain Clouds in this delivery.

## 15. Implementation authorization boundary

This specification records the product direction approved by the user. Implementation begins only
after written-spec review and a committed implementation plan. External account creation, Notion
public-connection configuration, deployment, DNS changes, and publication remain separate explicit
mutations. No paid resource may be created without new user authorization.
