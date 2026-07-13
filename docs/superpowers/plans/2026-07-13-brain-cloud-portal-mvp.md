# Brain Cloud Portal MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only, tenant-scoped Brain Cloud Portal with Framer Directory-inspired navigation, hybrid retrieval, cited AI answers, Obsidian ingestion, and guided Notion editing.

**Architecture:** Add a separate `brain_portal` Flask package and `portal_app.py`; do not add Portal routes to the existing LINE capture `app.py`. Canonical Obsidian or Notion documents are normalized into a tenant-scoped SQLite projection with FTS5 and 768-dimensional Gemini embeddings. Retrieval fuses lexical and vector rankings, and generation receives only cited, tenant-scoped evidence.

**Tech Stack:** Python 3.11, Flask 3.1, SQLite/FTS5, Gemini `gemini-embedding-001`, existing Gemini/DeepSeek generation failover, Requests, Jinja, vanilla CSS/JavaScript, Pytest.

## Global Constraints

- Kevin's Obsidian vault remains read-only and canonical.
- General users edit canonical guided Notion pages; Portal remains read-only.
- Every entity, index lookup, cache key, and answer request is tenant-scoped.
- No AI answer without Knowledge Item citations.
- Existing LINE capture behavior and `app.py` routes remain compatible.
- Portal UI uses Framer Directory-inspired editorial hierarchy, restrained Cloud color, and no raw database tables.
- MVP supports Web3, Food, and AI Automation only.
- Production signup, production OAuth, payments, sharing, and bidirectional sync remain excluded.

## File map

- `portal_app.py`: independent Portal process entrypoint.
- `brain_portal/config.py`: Portal-only configuration.
- `brain_portal/models.py`: immutable source, item, search, and answer contracts.
- `brain_portal/db.py`: tenant-scoped SQLite schema and transaction helpers.
- `brain_portal/tenant.py`: server-derived tenant context.
- `brain_portal/connectors/base.py`: connector protocol.
- `brain_portal/connectors/obsidian.py`: read-only Markdown source adapter.
- `brain_portal/connectors/notion.py`: Notion API source adapter and canonical edit URLs.
- `brain_portal/embeddings.py`: Gemini document/query embeddings and cosine similarity.
- `brain_portal/indexer.py`: normalization, chunking, idempotent upserts, soft deletion, and sync runs.
- `brain_portal/search.py`: FTS/vector fusion and tenant-scoped results.
- `brain_portal/answers.py`: cited answer generation and provider fallback.
- `brain_portal/web.py`: Portal Flask blueprint and view-model composition.
- `brain_portal/templates/portal/*.html`: home, Cloud, search, item, place, and sync pages.
- `brain_portal/static/portal.css`: Framer Directory-inspired responsive design system.
- `brain_portal/static/portal.js`: search/filter progressive enhancement.
- `tests/portal/`: isolated unit, security, integration, and browser-contract tests.

---

### Task 1: Tenant-scoped projection store

**Files:**
- Create: `brain_portal/__init__.py`
- Create: `brain_portal/config.py`
- Create: `brain_portal/models.py`
- Create: `brain_portal/db.py`
- Create: `brain_portal/tenant.py`
- Test: `tests/portal/test_db.py`
- Test: `tests/portal/test_tenant.py`

**Interfaces:**
- Produces: `PortalSettings`, `TenantContext`, `SourceDocument`, `KnowledgeItem`, `SearchHit`, `CitedAnswer`.
- Produces: `portal_connect(path)`, `init_portal_db(path)`, and tenant-scoped repository functions.
- Consumes: no Portal code from later tasks.

- [ ] **Step 1: Write failing tenant-isolation tests**

```python
# tests/portal/test_db.py
from brain_portal.db import PortalRepository, init_portal_db
from brain_portal.models import KnowledgeItem


def item(tenant_id: str, source_id: str, title: str) -> KnowledgeItem:
    return KnowledgeItem(
        tenant_id=tenant_id,
        source_id=source_id,
        source_type="obsidian",
        canonical_ref=f"obsidian://{source_id}",
        title=title,
        summary=f"{title} summary",
        body="body",
        cloud_key="ai",
        item_type="research",
        concepts=("AI Agents",),
        place=None,
        source_revision="rev-1",
        updated_at="2026-07-13T00:00:00+00:00",
    )


def test_repository_never_returns_another_tenant(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)
    repo.upsert_item(item("tenant-a", "same", "A only"), chunks=[])
    repo.upsert_item(item("tenant-b", "same", "B only"), chunks=[])

    assert [row.title for row in repo.list_items("tenant-a")] == ["A only"]
    assert [row.title for row in repo.list_items("tenant-b")] == ["B only"]
```

```python
# tests/portal/test_tenant.py
import pytest
from flask import Flask

from brain_portal.tenant import resolve_tenant


def test_tenant_comes_from_server_config_not_query_string():
    app = Flask(__name__)
    app.config.update(PORTAL_TENANT_ID="kevin", TESTING=False)
    with app.test_request_context("/?tenant_id=attacker"):
        assert resolve_tenant().tenant_id == "kevin"


def test_missing_tenant_is_rejected():
    app = Flask(__name__)
    with app.test_request_context("/"):
        with pytest.raises(PermissionError):
            resolve_tenant()
```

- [ ] **Step 2: Run tests and verify the package is missing**

Run: `pytest tests/portal/test_db.py tests/portal/test_tenant.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'brain_portal'`.

- [ ] **Step 3: Implement immutable contracts and configuration**

```python
# brain_portal/models.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    display_name: str


@dataclass(frozen=True)
class SourceDocument:
    tenant_id: str
    source_id: str
    source_type: str
    canonical_ref: str
    title: str
    body: str
    cloud_key: str
    source_revision: str
    updated_at: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class KnowledgeItem:
    tenant_id: str
    source_id: str
    source_type: str
    canonical_ref: str
    title: str
    summary: str
    body: str
    cloud_key: str
    item_type: str
    concepts: tuple[str, ...]
    place: dict[str, object] | None
    source_revision: str
    updated_at: str


@dataclass(frozen=True)
class SearchHit:
    item: KnowledgeItem
    score: float
    matched_by: tuple[str, ...]


@dataclass(frozen=True)
class CitedAnswer:
    text: str
    source_ids: tuple[str, ...]
    provider: str
    degraded: bool = False
```

```python
# brain_portal/config.py
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PortalSettings:
    database_path: str = os.getenv("PORTAL_DATABASE_PATH", "data/brain-portal.sqlite3")
    tenant_id: str = os.getenv("PORTAL_TENANT_ID", "")
    tenant_name: str = os.getenv("PORTAL_TENANT_NAME", "Kevin's Brain")
    obsidian_root: str = os.getenv("PORTAL_OBSIDIAN_ROOT", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    notion_token: str = os.getenv("NOTION_TOKEN", "")
    notion_api_version: str = "2026-03-11"
```

- [ ] **Step 4: Implement the schema, repository, and tenant resolver**

```python
# brain_portal/tenant.py
from flask import current_app
from brain_portal.models import TenantContext


def resolve_tenant() -> TenantContext:
    tenant_id = str(current_app.config.get("PORTAL_TENANT_ID") or "").strip()
    if not tenant_id:
        raise PermissionError("tenant context is required")
    return TenantContext(
        tenant_id=tenant_id,
        display_name=str(current_app.config.get("PORTAL_TENANT_NAME") or tenant_id),
    )
```

Implement `brain_portal/db.py` with tables `tenants`, `source_connections`, `knowledge_items`,
`knowledge_chunks`, `item_concepts`, `places`, and `sync_runs`. Use composite primary keys beginning
with `tenant_id`; every repository method accepts `tenant_id` explicitly. Create an FTS5 virtual
table keyed by an internal numeric chunk row id, plus triggers or explicit repository updates.

- [ ] **Step 5: Run focused and existing tests**

Run: `pytest tests/portal/test_db.py tests/portal/test_tenant.py -q`

Expected: `4 passed`.

Run: `pytest -q`

Expected: all pre-existing tests and Portal tests pass.

- [ ] **Step 6: Commit the store boundary**

```bash
git add brain_portal tests/portal/test_db.py tests/portal/test_tenant.py
git commit -m "feat: add tenant-scoped portal store"
```

---

### Task 2: Read-only Obsidian ingestion and idempotent indexing

**Files:**
- Create: `brain_portal/connectors/__init__.py`
- Create: `brain_portal/connectors/base.py`
- Create: `brain_portal/connectors/obsidian.py`
- Create: `brain_portal/indexer.py`
- Test: `tests/portal/test_obsidian_connector.py`
- Test: `tests/portal/test_indexer.py`

**Interfaces:**
- Consumes: `SourceDocument`, `KnowledgeItem`, `PortalRepository` from Task 1.
- Produces: `SourceConnector.iter_documents(tenant_id: str) -> Iterable[SourceDocument]`.
- Produces: `normalize_document(doc: SourceDocument) -> KnowledgeItem`.
- Produces: `run_index(tenant_id: str, connector: SourceConnector, repo: PortalRepository, embedder: EmbeddingProvider) -> IndexReport`.

- [ ] **Step 1: Write failing read-only and idempotency tests**

```python
# tests/portal/test_obsidian_connector.py
from brain_portal.connectors.obsidian import ObsidianConnector


def test_connector_maps_folder_to_cloud_without_writing(tmp_path):
    root = tmp_path / "Kevin_Brain"
    note = root / "50_Tech_AI自動化" / "Claude Code.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Claude Code\n\nAgent workflow", encoding="utf-8")
    before = note.stat().st_mtime_ns

    docs = list(ObsidianConnector(root).iter_documents("kevin"))

    assert docs[0].cloud_key == "ai"
    assert docs[0].canonical_ref.endswith("50_Tech_AI自動化/Claude Code.md")
    assert note.stat().st_mtime_ns == before
```

```python
# tests/portal/test_indexer.py
def test_reindexing_same_revision_is_idempotent(portal_repo, fake_connector):
    first = run_index("kevin", fake_connector, portal_repo, fake_embedder)
    second = run_index("kevin", fake_connector, portal_repo, fake_embedder)

    assert first.indexed == 1
    assert second.unchanged == 1
    assert len(portal_repo.list_items("kevin")) == 1
```

- [ ] **Step 2: Run tests and verify missing connector/indexer failures**

Run: `pytest tests/portal/test_obsidian_connector.py tests/portal/test_indexer.py -q`

Expected: collection errors for the missing modules.

- [ ] **Step 3: Implement connector protocol and Obsidian adapter**

```python
# brain_portal/connectors/base.py
from typing import Protocol, Iterable
from brain_portal.models import SourceDocument


class SourceConnector(Protocol):
    def iter_documents(self, tenant_id: str) -> Iterable[SourceDocument]: ...
```

`ObsidianConnector` must resolve every file under the configured root, accept only `.md`, reject
symlinks escaping the root, skip hidden paths plus `instructions.md`, and map only these MVP folders:
`11_Web3_商業研究 -> web3`, `50_Tech_AI自動化 -> ai`, `71_Food_美食與咖啡地圖 -> food`.
The revision is SHA-256 of file bytes; the adapter never opens a file for writing.

- [ ] **Step 4: Implement normalization and atomic indexing**

```python
# brain_portal/indexer.py
from dataclasses import dataclass


@dataclass(frozen=True)
class IndexReport:
    indexed: int
    unchanged: int
    deleted: int
    failed: int


def normalize_document(doc: SourceDocument) -> KnowledgeItem:
    paragraphs = [part.strip() for part in doc.body.split("\n\n") if part.strip()]
    summary = next((p for p in paragraphs if not p.startswith("#")), doc.title)[:500]
    return KnowledgeItem(
        tenant_id=doc.tenant_id,
        source_id=doc.source_id,
        source_type=doc.source_type,
        canonical_ref=doc.canonical_ref,
        title=doc.title,
        summary=summary,
        body=doc.body,
        cloud_key=doc.cloud_key,
        item_type=str(doc.metadata.get("item_type") or "research"),
        concepts=tuple(doc.metadata.get("concepts") or ()),
        place=doc.metadata.get("place") if isinstance(doc.metadata.get("place"), dict) else None,
        source_revision=doc.source_revision,
        updated_at=doc.updated_at,
    )
```

`run_index()` must create a sync run, skip unchanged revisions, chunk changed documents, embed chunks,
upsert in a single tenant transaction, soft-delete missing source ids only after a successful scan,
and leave the last successful projection intact if the connector raises before completion.

- [ ] **Step 5: Run connector/indexer and regression tests**

Run: `pytest tests/portal/test_obsidian_connector.py tests/portal/test_indexer.py -q`

Expected: all tests pass, including read-only mtime and idempotency assertions.

Run: `pytest -q`

Expected: full suite passes.

- [ ] **Step 6: Commit ingestion**

```bash
git add brain_portal/connectors brain_portal/indexer.py tests/portal
git commit -m "feat: index canonical Obsidian notes"
```

---

### Task 3: Hybrid lexical and semantic retrieval

**Files:**
- Create: `brain_portal/embeddings.py`
- Create: `brain_portal/search.py`
- Modify: `brain_portal/config.py`
- Test: `tests/portal/test_embeddings.py`
- Test: `tests/portal/test_search.py`

**Interfaces:**
- Consumes: chunks and tenant repository from Tasks 1–2.
- Produces: `EmbeddingProvider.embed(text: str, task_type: str) -> list[float]`.
- Produces: `cosine_similarity(left: list[float], right: list[float]) -> float`.
- Produces: `hybrid_search(repo: PortalRepository, embedder: EmbeddingProvider, tenant_id: str, query: str, cloud_key: str | None, limit: int = 10) -> list[SearchHit]`.

- [ ] **Step 1: Write failing embedding and search tests**

```python
# tests/portal/test_search.py
def test_hybrid_search_filters_before_ranking(portal_repo, seeded_two_tenants, fake_embedder):
    hits = hybrid_search(
        repo=portal_repo,
        embedder=fake_embedder,
        tenant_id="tenant-a",
        query="agent workflow",
        cloud_key="ai",
        limit=5,
    )
    assert hits
    assert {hit.item.tenant_id for hit in hits} == {"tenant-a"}
    assert hits[0].item.title == "Agent workflow"


def test_vector_failure_degrades_to_lexical(portal_repo, seeded_ai_item):
    hits = hybrid_search(portal_repo, FailingEmbedder(), "kevin", "Claude", None, 5)
    assert hits[0].matched_by == ("lexical",)
```

- [ ] **Step 2: Run tests and verify missing retrieval modules**

Run: `pytest tests/portal/test_embeddings.py tests/portal/test_search.py -q`

Expected: collection fails for missing `brain_portal.embeddings` and `brain_portal.search`.

- [ ] **Step 3: Implement Gemini embeddings and cosine similarity**

```python
# brain_portal/embeddings.py
import math
import requests


class GeminiEmbeddingProvider:
    def __init__(self, api_key: str, timeout: int = 25):
        self.api_key = api_key
        self.timeout = timeout

    def embed(self, text: str, task_type: str) -> list[float]:
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-embedding-001:embedContent",
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            json={
                "model": "models/gemini-embedding-001",
                "taskType": task_type,
                "outputDimensionality": 768,
                "content": {"parts": [{"text": text[:8000]}]},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return [float(value) for value in response.json()["embedding"]["values"]]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    denominator = math.sqrt(sum(x * x for x in left)) * math.sqrt(sum(x * x for x in right))
    return sum(x * y for x, y in zip(left, right)) / denominator if denominator else 0.0
```

Use `RETRIEVAL_DOCUMENT` during indexing and `RETRIEVAL_QUERY` during search, following the official
Gemini embedding contract. Persist the model id and dimensions with every vector so incompatible
embedding spaces cannot be mixed.

- [ ] **Step 4: Implement reciprocal-rank fusion**

`hybrid_search()` first asks the repository for tenant-and-filter-constrained lexical and vector
candidates. Fuse ranks with `1 / (60 + rank)`, deduplicate by `(tenant_id, source_id)`, and return
`SearchHit` objects. If query embedding fails, use lexical candidates and add a degraded-search flag
to the search response view model.

- [ ] **Step 5: Run retrieval and full tests**

Run: `pytest tests/portal/test_embeddings.py tests/portal/test_search.py -q`

Expected: hybrid, filter, tenant, and degradation tests pass.

Run: `pytest -q`

Expected: full suite passes.

- [ ] **Step 6: Commit retrieval**

```bash
git add brain_portal/embeddings.py brain_portal/search.py brain_portal/config.py tests/portal
git commit -m "feat: add tenant-safe hybrid retrieval"
```

---

### Task 4: Grounded answers with citation enforcement

**Files:**
- Create: `brain_portal/answers.py`
- Test: `tests/portal/test_answers.py`

**Interfaces:**
- Consumes: `SearchHit` from Task 3 and existing Gemini/DeepSeek credentials.
- Produces: `AnswerProvider.generate(prompt: str) -> tuple[str, str]`, returning response text and provider name.
- Produces: `answer_query(query: str, hits: list[SearchHit], provider_chain: list[AnswerProvider]) -> CitedAnswer | None`.

- [ ] **Step 1: Write failing citation and fallback tests**

```python
def test_answer_rejects_uncited_claim(fake_hits):
    provider = FakeProvider('{"answer":"Agents are faster","citations":[]}')
    assert answer_query("What changed?", fake_hits, [provider]) is None


def test_provider_failure_returns_source_only_state(fake_hits):
    answer = answer_query("What changed?", fake_hits, [FailingProvider(), FailingProvider()])
    assert answer is None


def test_answer_accepts_only_retrieved_source_ids(fake_hits):
    provider = FakeProvider('{"answer":"Work becomes delegated [1]","citations":["item-1"]}')
    answer = answer_query("What changed?", fake_hits, [provider])
    assert answer.source_ids == ("item-1",)
```

- [ ] **Step 2: Run tests and verify missing answer service**

Run: `pytest tests/portal/test_answers.py -q`

Expected: import failure for `brain_portal.answers`.

- [ ] **Step 3: Implement evidence packaging and strict parsing**

Build a numbered evidence payload containing only each hit's `source_id`, title, summary, and bounded
body excerpt. Require JSON `{"answer": str, "citations": [source_id, ...]}`. Reject empty citations,
unknown ids, malformed JSON, and answers when `hits` is empty. Try Gemini, then DeepSeek; return `None`
after both fail so the web layer can show source cards without fabricating an answer.

- [ ] **Step 4: Run answer and full tests**

Run: `pytest tests/portal/test_answers.py -q`

Expected: all citation and fallback tests pass.

Run: `pytest -q`

Expected: full suite passes.

- [ ] **Step 5: Commit grounded answers**

```bash
git add brain_portal/answers.py tests/portal/test_answers.py
git commit -m "feat: enforce citations in portal answers"
```

---

### Task 5: Framer Directory-inspired Portal web experience

**Files:**
- Create: `portal_app.py`
- Create: `brain_portal/web.py`
- Create: `brain_portal/templates/portal/base.html`
- Create: `brain_portal/templates/portal/home.html`
- Create: `brain_portal/templates/portal/search.html`
- Create: `brain_portal/templates/portal/cloud.html`
- Create: `brain_portal/templates/portal/item.html`
- Create: `brain_portal/templates/portal/place.html`
- Create: `brain_portal/templates/portal/sync.html`
- Create: `brain_portal/static/portal.css`
- Create: `brain_portal/static/portal.js`
- Test: `tests/portal/test_web.py`
- Test: `tests/portal/test_accessibility.py`

**Interfaces:**
- Consumes: repository, tenant resolver, hybrid search, and answer service.
- Produces: independent Flask app with `/`, `/search`, `/cloud/<key>`, `/item/<source_id>`, `/place/<source_id>`, and `/sync`.

- [ ] **Step 1: Write failing route and content-order tests**

```python
def test_home_leads_with_search_then_intents_then_clouds(portal_client):
    html = portal_client.get("/").get_data(as_text=True)
    assert html.index('id="brain-search"') < html.index('id="intent-shortcuts"')
    assert html.index('id="intent-shortcuts"') < html.index('id="cloud-gallery"')
    assert "Knowledge Items" not in html


def test_item_is_answer_first_and_has_canonical_action(portal_client):
    html = portal_client.get("/item/ai-agent").get_data(as_text=True)
    assert html.index('id="item-answer"') < html.index('id="item-metadata"')
    assert "Open in Obsidian" in html


def test_search_has_citations_and_source_cards(portal_client):
    html = portal_client.get("/search?q=agent").get_data(as_text=True)
    assert 'id="answer-citations"' in html
    assert 'data-source-id="ai-agent"' in html
```

- [ ] **Step 2: Run tests and verify the independent app is missing**

Run: `pytest tests/portal/test_web.py tests/portal/test_accessibility.py -q`

Expected: import or route failures because `portal_app.py` and templates do not exist.

- [ ] **Step 3: Implement the independent app and routes**

```python
# portal_app.py
from flask import Flask
from brain_portal.config import PortalSettings
from brain_portal.web import create_portal_blueprint


def create_app(settings: PortalSettings | None = None) -> Flask:
    settings = settings or PortalSettings()
    app = Flask(__name__)
    app.config.update(
        PORTAL_DATABASE_PATH=settings.database_path,
        PORTAL_TENANT_ID=settings.tenant_id,
        PORTAL_TENANT_NAME=settings.tenant_name,
    )
    app.register_blueprint(create_portal_blueprint())
    return app


app = create_app()
```

Use route-specific view models; templates do not call repositories. Return 404 for an item outside
the resolved tenant even when the same `source_id` exists for another tenant.

- [ ] **Step 4: Implement the approved visual hierarchy**

Create semantic HTML with a skip link, one `h1`, visible focus states, keyboard-operable filters,
and 44px minimum touch targets. CSS uses editorial typography, neutral surfaces, restrained per-Cloud
accent variables, fluid grid cards, and responsive breakpoints at 760px and 1080px. Do not reproduce
Framer proprietary assets or code; use only the approved visual principles.

- [ ] **Step 5: Run route, accessibility-contract, and full tests**

Run: `pytest tests/portal/test_web.py tests/portal/test_accessibility.py -q`

Expected: route order, tenant 404, labels, heading order, and canonical action tests pass.

Run: `pytest -q`

Expected: full suite passes.

- [ ] **Step 6: Launch locally and verify the complete flow**

Run: `PORTAL_TENANT_ID=kevin PORTAL_DATABASE_PATH=data/brain-portal.sqlite3 flask --app portal_app run --port 5050`

Expected: the Portal serves at `http://127.0.0.1:5050` without altering the LINE capture process.

- [ ] **Step 7: Commit the Portal UI**

```bash
git add portal_app.py brain_portal/web.py brain_portal/templates brain_portal/static tests/portal
git commit -m "feat: add brain cloud portal experience"
```

---

### Task 6: Guided Notion editing and incremental re-indexing

**Files:**
- Create: `brain_portal/connectors/notion.py`
- Create: `brain_portal/notion_webhook.py`
- Modify: `brain_portal/indexer.py`
- Modify: `brain_portal/web.py`
- Test: `tests/portal/test_notion_connector.py`
- Test: `tests/portal/test_notion_webhook.py`

**Interfaces:**
- Consumes: connector protocol, indexer, tenant store, and item view models.
- Produces: `NotionConnector`, `verify_notion_webhook()`, and an idempotent page re-index signal.

- [ ] **Step 1: Write failing canonical-edit and webhook tests**

```python
def test_notion_item_exposes_direct_page_edit_url(notion_connector):
    [doc] = list(notion_connector.iter_documents("tenant-notion"))
    assert doc.canonical_ref == "https://www.notion.so/example-page-id"


def test_webhook_is_only_a_signal(fake_notion_api, portal_repo):
    response = notion_webhook_client.post(
        "/hooks/notion",
        json={"type": "page.content_updated", "entity": {"id": "page-1"}},
        headers={"X-Notion-Signature": "valid"},
    )
    assert response.status_code == 202
    assert fake_notion_api.retrieve_calls == ["page-1"]
    assert portal_repo.get_item("tenant-notion", "page-1").source_revision == "new-revision"
```

- [ ] **Step 2: Run tests and verify missing Notion modules**

Run: `pytest tests/portal/test_notion_connector.py tests/portal/test_notion_webhook.py -q`

Expected: import failures for the missing connector and webhook handler.

- [ ] **Step 3: Implement the Notion connector**

Use `Authorization: Bearer`, `Notion-Version: 2026-03-11`, and explicit timeouts. Retrieve pages and
their block children, following pagination. Read only the approved guided properties: title, Summary,
Cloud, Concepts, and page body. Preserve the public page URL as `canonical_ref`; do not copy connector
credentials or hidden system properties into indexed content.

- [ ] **Step 4: Implement verified webhook signaling and targeted re-indexing**

Verify the Notion webhook signature before reading the payload. Treat `page.content_updated` and
`page.properties_updated` as signals, retrieve the current page through the connector, and invoke an
idempotent single-document indexing path. Return 202 after the update is durably queued or completed;
return 401 for invalid signatures. The handler never trusts content in the webhook body as canonical.

- [ ] **Step 5: Show guided edit state in the Portal**

For Notion-backed items render `Edit in Notion`; for Kevin's Obsidian items render `Open in Obsidian`.
Render `Syncing`, `Up to date`, `Stale`, or `Permission required` from persisted sync state. Hide all
system properties from the item page.

- [ ] **Step 6: Run Notion, security, and full tests**

Run: `pytest tests/portal/test_notion_connector.py tests/portal/test_notion_webhook.py tests/portal/test_web.py -q`

Expected: canonical URL, signature, re-fetch, tenant, status, and hidden-field tests pass.

Run: `pytest -q`

Expected: full suite passes.

- [ ] **Step 7: Commit Notion editing**

```bash
git add brain_portal/connectors/notion.py brain_portal/notion_webhook.py brain_portal/indexer.py brain_portal/web.py tests/portal
git commit -m "feat: sync guided Notion edits"
```

---

### Task 7: End-to-end verification, operations, and recovery

**Files:**
- Create: `scripts/index_brain_portal.py`
- Create: `scripts/verify_brain_portal.py`
- Create: `tests/portal/test_security_e2e.py`
- Create: `tests/portal/test_reliability_e2e.py`
- Modify: `.env.example`
- Modify: `render.yaml`
- Modify: `README.md`
- Modify: `GO_LIVE.md`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: repeatable index command, verification report, separate Render service declaration, and operator recovery steps.

- [ ] **Step 1: Write failing security and recovery tests**

```python
def test_same_query_never_crosses_tenants(portal_factory):
    tenant_a = portal_factory("tenant-a")
    tenant_b = portal_factory("tenant-b")
    assert "B secret" not in tenant_a.get("/search?q=shared").get_data(as_text=True)
    assert "A secret" not in tenant_b.get("/search?q=shared").get_data(as_text=True)


def test_failed_sync_keeps_last_successful_projection(index_fixture):
    index_fixture.run_successfully()
    previous = index_fixture.repo.list_items("kevin")
    index_fixture.connector.fail_next_scan()
    report = index_fixture.run()
    assert report.failed == 1
    assert index_fixture.repo.list_items("kevin") == previous
    assert index_fixture.repo.latest_sync("kevin").status == "stale"
```

- [ ] **Step 2: Run end-to-end tests and verify missing scripts/behaviors**

Run: `pytest tests/portal/test_security_e2e.py tests/portal/test_reliability_e2e.py -q`

Expected: failures until scripts, status handling, and final wiring exist.

- [ ] **Step 3: Implement operator commands**

`scripts/index_brain_portal.py` accepts `--tenant`, exactly one of `--obsidian-root` or
`--notion-connection`, and `--dry-run`. `scripts/verify_brain_portal.py` checks tenant counts, missing
canonical refs, embedding model consistency, stale syncs, uncited cached answers, and source
read-only status; it prints a JSON report and exits nonzero on failure.

- [ ] **Step 4: Add configuration and separate service documentation**

Add these names only to `.env.example`: `PORTAL_DATABASE_PATH`, `PORTAL_TENANT_ID`,
`PORTAL_TENANT_NAME`, `PORTAL_OBSIDIAN_ROOT`, `NOTION_WEBHOOK_SECRET`. Do not add values from `.env`.
Add a separate `brain-cloud-portal` Render service using `gunicorn portal_app:app`; do not change the
existing `line-notion-capture` start command. Document local index, local serve, verification, stale
recovery, and rollback commands.

- [ ] **Step 5: Run the full automated gate**

Run: `pytest -q`

Expected: zero failures.

Run: `python scripts/verify_brain_portal.py --tenant kevin --database data/brain-portal.sqlite3`

Expected: JSON with `"valid": true`, zero tenant leaks, zero missing canonical refs, and zero uncited answers.

Run: `git diff --check`

Expected: no output and exit code 0.

- [ ] **Step 6: Perform browser verification**

Start the Portal locally and verify these stories at desktop and mobile widths:

1. Home → AI Cloud in at most one click.
2. Search `Web3 賽道` → cited answer plus source cards.
3. Food Cloud → map/place result in at most three interactions.
4. Knowledge Item → answer before metadata → canonical edit action.
5. Simulated stale sync → visible `Stale` status with last successful timestamp.

Expected: each story meets the design acceptance criteria without exposing a raw database table.

- [ ] **Step 7: Commit operations and verification**

```bash
git add scripts/index_brain_portal.py scripts/verify_brain_portal.py tests/portal .env.example render.yaml README.md GO_LIVE.md
git commit -m "docs: add portal verification and operations"
```

## Plan self-review checklist

- Each design section maps to at least one task: UX (Task 5), indexing (Tasks 1–3), grounded answers
  (Task 4), canonical editing (Task 6), failures/security/acceptance (Tasks 1, 6, 7).
- All cross-task interfaces use the names defined in Tasks 1–4.
- Every task begins with a failing test, records the expected failure, implements the smallest
  boundary, runs focused plus regression tests, and ends with an intentional commit.
- No implementation task mutates canonical Obsidian content or existing Notion content.
- The plan contains no production deployment, purchase, public signup, or bidirectional sync step.
