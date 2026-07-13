from __future__ import annotations

import re

import pytest

import portal_app
from brain_portal.config import PortalSettings
from brain_portal.models import CitedAnswer, KnowledgeItem, SearchHit, TenantContext
from brain_portal.search import SearchResults
from brain_portal.web import PortalDependencies
from portal_app import create_app


def item(
    source_id: str,
    *,
    tenant_id: str = "kevin",
    source_type: str = "obsidian",
    canonical_ref: str | None = None,
    cloud_key: str = "ai",
    place: dict[str, object] | None = None,
    item_type: str = "research",
    concepts: tuple[str, ...] = ("agents", "reliability"),
    updated_at: str = "2026-07-13T10:30:00+00:00",
    body: str = "Evidence, observations, and practical next steps.",
) -> KnowledgeItem:
    return KnowledgeItem(
        tenant_id=tenant_id,
        source_id=source_id,
        source_type=source_type,
        canonical_ref=canonical_ref or f"obsidian://open?vault=Brain&file={source_id}",
        title={
            "ai-agent": "Reliable agent systems",
            "folder/note.md": "Nested research note",
            "notion-page": "Shared workflow",
            "food-place": "Quiet noodle shop",
        }.get(source_id, "Private note"),
        summary="A source-backed summary for this note.",
        body=body,
        cloud_key=cloud_key,
        item_type=item_type,
        concepts=concepts,
        place=place,
        source_revision="rev-1",
        updated_at=updated_at,
    )


class FakeRepository:
    def __init__(self):
        self.items = [
            item("ai-agent"),
            item("folder/note.md"),
            item(
                "notion-page",
                source_type="notion",
                canonical_ref="https://www.notion.so/notion-page",
            ),
            item(
                "food-place",
                cloud_key="food",
                place={"name": "Quiet noodle shop", "area": "Da'an"},
            ),
            item("secret", tenant_id="other-tenant"),
        ]
        self.tenant_calls = []

    def list_items(self, tenant_id: str):
        self.tenant_calls.append(tenant_id)
        return list(self.items)


class TenantResolver:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return TenantContext("kevin", "Kevin's Brain")


class SearchService:
    def __init__(self, degraded=True):
        self.calls = []
        self.degraded = degraded

    def __call__(self, tenant_id: str, query: str, cloud_key: str | None):
        self.calls.append((tenant_id, query, cloud_key))
        return SearchResults(
            hits=(SearchHit(item("ai-agent"), 1.0, ("lexical",)),),
            degraded=self.degraded,
        )


class AnswerService:
    def __init__(self, answer=True):
        self.calls = []
        self.answer = answer

    def __call__(self, query: str, hits: list[SearchHit]):
        self.calls.append((query, hits))
        if not self.answer:
            return None
        return CitedAnswer(
            text="Reliable agents pair clear boundaries with observable fallbacks.",
            source_ids=("ai-agent",),
            provider="gemini",
        )


@pytest.fixture
def portal_setup():
    repository = FakeRepository()
    resolver = TenantResolver()
    search = SearchService()
    answers = AnswerService()
    app = create_app(
        dependencies=PortalDependencies(repository, resolver, search, answers)
    )
    app.config.update(TESTING=True)
    return app.test_client(), repository, resolver, search, answers


def test_home_leads_with_search_then_intents_then_clouds_then_recent(portal_setup):
    client, *_ = portal_setup

    html = client.get("/").get_data(as_text=True)

    assert html.index('id="brain-search"') < html.index('id="intent-shortcuts"')
    assert html.index('id="intent-shortcuts"') < html.index('id="cloud-gallery"')
    assert html.index('id="cloud-gallery"') < html.index('id="recent-notes"')
    assert "Knowledge Items" not in html
    assert "Find a useful note, then follow its sources." in html


def test_all_routes_resolve_the_mandatory_tenant(portal_setup):
    client, repository, resolver, *_ = portal_setup
    paths = [
        "/",
        "/search?q=agent",
        "/cloud/ai",
        "/item/ai-agent",
        "/place/food-place",
        "/sync",
    ]

    responses = [client.get(path) for path in paths]

    assert [response.status_code for response in responses] == [200] * len(paths)
    assert resolver.calls == len(paths)
    assert repository.tenant_calls == ["kevin"] * len(paths)


def test_missing_tenant_is_rejected_before_repository_access():
    repository = FakeRepository()
    app = create_app(
        dependencies=PortalDependencies(
            repository,
            lambda: None,
            SearchService(),
            AnswerService(),
        )
    )
    app.config.update(TESTING=True)

    response = app.test_client().get("/")

    assert response.status_code == 401
    assert repository.tenant_calls == []


def test_cross_tenant_item_is_404_even_if_repository_returns_it(portal_setup):
    client, *_ = portal_setup

    assert client.get("/item/secret").status_code == 404
    assert client.get("/place/secret").status_code == 404


def test_item_route_supports_source_ids_with_slashes(portal_setup):
    client, *_ = portal_setup

    response = client.get("/item/folder/note.md")

    assert response.status_code == 200
    assert "Nested research note" in response.get_data(as_text=True)


def test_search_has_degraded_state_citations_and_source_cards(portal_setup):
    client, _, _, search, answers = portal_setup

    html = client.get("/search?q=agent&cloud=ai").get_data(as_text=True)

    assert 'id="retrieval-status"' in html
    assert "Keyword results are available while semantic search recovers." in html
    assert 'id="answer-citations"' in html
    assert 'href="/item/ai-agent"' in html
    assert 'data-source-id="ai-agent"' in html
    assert search.calls == [("kevin", "agent", "ai")]
    assert answers.calls[0][0] == "agent"


def test_search_provider_failure_shows_explicit_source_only_state():
    app = create_app(
        dependencies=PortalDependencies(
            FakeRepository(), TenantResolver(), SearchService(False), AnswerService(False)
        )
    )
    app.config.update(TESTING=True)

    html = app.test_client().get("/search?q=agent").get_data(as_text=True)

    assert 'id="source-only-state"' in html
    assert "No supported answer is available. Review the closest sources below." in html
    assert 'data-source-id="ai-agent"' in html


def test_blank_search_has_empty_state_and_does_not_call_services(portal_setup):
    client, _, _, search, answers = portal_setup

    html = client.get("/search").get_data(as_text=True)

    assert 'id="search-empty-state"' in html
    assert "Describe what you want to find." in html
    assert search.calls == []
    assert answers.calls == []


def test_search_error_has_actionable_error_contract():
    def failing_search(tenant_id, query, cloud_key):
        raise RuntimeError("private provider detail")

    app = create_app(
        dependencies=PortalDependencies(
            FakeRepository(), TenantResolver(), failing_search, AnswerService()
        )
    )
    app.config.update(TESTING=True)

    response = app.test_client().get("/search?q=agent")
    html = response.get_data(as_text=True)

    assert response.status_code == 503
    assert 'id="search-error-state"' in html
    assert "Search is temporarily unavailable. Try again in a moment." in html
    assert "private provider detail" not in html


def test_item_is_answer_first_and_has_obsidian_action(portal_setup):
    client, *_ = portal_setup

    html = client.get("/item/ai-agent").get_data(as_text=True)

    assert html.index('id="item-answer"') < html.index('id="item-metadata"')
    assert "Open in Obsidian" in html
    assert 'href="obsidian://open?vault=Brain&amp;file=ai-agent"' in html


def test_notion_item_has_direct_edit_action(portal_setup):
    client, *_ = portal_setup

    html = client.get("/item/notion-page").get_data(as_text=True)

    assert "Edit in Notion" in html
    assert 'href="https://www.notion.so/notion-page"' in html


def test_cloud_has_domain_filters_and_featured_paths(portal_setup):
    client, *_ = portal_setup

    html = client.get("/cloud/ai").get_data(as_text=True)

    assert 'id="cloud-filters"' in html
    assert "Tool" in html
    assert "Workflow" in html
    assert 'id="featured-paths"' in html
    assert "Build reliable agents" in html
    assert 'data-source-id="ai-agent"' in html


def test_place_and_sync_pages_use_reader_facing_states(portal_setup):
    client, *_ = portal_setup

    place_html = client.get("/place/food-place").get_data(as_text=True)
    sync_html = client.get("/sync").get_data(as_text=True)

    assert "Da&#39;an" in place_html
    assert "Open source note" in place_html
    assert 'id="sync-status"' in sync_html
    assert "Up to date" in sync_html


def test_default_dependencies_wire_hybrid_search_and_ordered_answer_chain(monkeypatch):
    repository = FakeRepository()
    embedder = object()
    gemini_provider = object()
    deepseek_provider = object()
    calls = {"hybrid": [], "answer": []}

    monkeypatch.setattr(portal_app, "PortalRepository", lambda path: repository)
    monkeypatch.setattr(
        portal_app, "GeminiEmbeddingProvider", lambda key, timeout: embedder
    )
    monkeypatch.setattr(
        portal_app,
        "GeminiAnswerProvider",
        lambda key, timeout, model: gemini_provider,
    )
    monkeypatch.setattr(
        portal_app,
        "DeepSeekAnswerProvider",
        lambda key, timeout, model: deepseek_provider,
    )

    def fake_hybrid(repo, active_embedder, tenant_id, query, cloud_key):
        calls["hybrid"].append(
            (repo, active_embedder, tenant_id, query, cloud_key)
        )
        return SearchResults(())

    def fake_answer(query, hits, providers):
        calls["answer"].append((query, hits, providers))
        return None

    monkeypatch.setattr(portal_app, "hybrid_search", fake_hybrid)
    monkeypatch.setattr(portal_app, "answer_query", fake_answer)
    settings = PortalSettings(
        database_path="portal.sqlite3",
        tenant_id="kevin",
        gemini_api_key="gemini-test-key",
        deepseek_api_key="deepseek-test-key",
        ai_timeout_seconds=9.0,
        gemini_answer_model="gemini-test-model",
        deepseek_answer_model="deepseek-test-model",
    )

    dependencies = portal_app._default_dependencies(settings)
    dependencies.search_service("kevin", "agents", "ai")
    dependencies.answer_service("agents", [])

    assert calls["hybrid"] == [
        (repository, embedder, "kevin", "agents", "ai")
    ]
    assert calls["answer"] == [("agents", [], [gemini_provider, deepseek_provider])]


def test_default_dependencies_without_keys_are_lexical_degraded_and_source_only(
    monkeypatch
):
    repository = FakeRepository()
    lexical_hit = SearchHit(item("ai-agent"), 2.0, ("lexical",))
    repository.lexical_search = lambda tenant_id, query, cloud_key=None: [lexical_hit]
    monkeypatch.setattr(portal_app, "PortalRepository", lambda path: repository)
    monkeypatch.setattr(
        portal_app,
        "GeminiEmbeddingProvider",
        lambda *args, **kwargs: pytest.fail("embedding provider must not be created"),
        raising=False,
    )
    settings = PortalSettings(
        database_path="portal.sqlite3",
        tenant_id="kevin",
        gemini_api_key="",
        deepseek_api_key="",
    )

    dependencies = portal_app._default_dependencies(settings)
    results = dependencies.search_service("kevin", "agents", None)

    assert results.hits == (lexical_hit,)
    assert results.degraded is True
    assert dependencies.answer_service("agents", [lexical_hit]) is None


def test_search_rebuilds_raw_hit_from_repository_before_answer_and_render():
    repository = FakeRepository()
    poisoned = item("ai-agent")
    poisoned = KnowledgeItem(
        **{
            **poisoned.__dict__,
            "title": "INJECTED TITLE",
            "summary": "INJECTED SUMMARY",
            "body": "INJECTED BODY",
        }
    )
    captured = []

    def poisoned_search(tenant_id, query, cloud_key):
        return SearchResults((SearchHit(poisoned, 7.5, ("semantic",)),))

    def capture_answer(query, hits):
        captured.extend(hits)
        return None

    app = create_app(
        dependencies=PortalDependencies(
            repository, TenantResolver(), poisoned_search, capture_answer
        )
    )
    app.config.update(TESTING=True)

    html = app.test_client().get("/search?q=agent").get_data(as_text=True)

    assert captured == [
        SearchHit(repository.items[0], 7.5, ("semantic",))
    ]
    assert "Reliable agent systems" in html
    assert "INJECTED" not in html


@pytest.mark.parametrize(
    ("source_type", "canonical_ref"),
    [
        ("obsidian", "javascript:alert(1)"),
        ("obsidian", "https://www.notion.so/page"),
        ("notion", "http://www.notion.so/page"),
        ("notion", "https://evilnotion.so/page"),
        ("notion", "https://notion.so.evil.example/page"),
        ("notion", "javascript:alert(1)"),
        ("notion", "data:text/html,bad"),
        ("notion", "file:///private/note"),
        ("other", "https://www.notion.so/page"),
    ],
)
def test_item_and_place_hide_untrusted_canonical_actions(source_type, canonical_ref):
    unsafe = item(
        "unsafe",
        source_type=source_type,
        canonical_ref=canonical_ref,
        cloud_key="food",
        place={"name": "Unsafe place"},
    )
    repository = FakeRepository()
    repository.items = [unsafe]
    app = create_app(
        dependencies=PortalDependencies(
            repository, TenantResolver(), SearchService(), AnswerService()
        )
    )
    app.config.update(TESTING=True)

    item_html = app.test_client().get("/item/unsafe").get_data(as_text=True)
    place_html = app.test_client().get("/place/unsafe").get_data(as_text=True)

    assert canonical_ref not in item_html
    assert canonical_ref not in place_html
    assert "Open in Obsidian" not in item_html
    assert "Edit in Notion" not in item_html
    assert "Open source note" not in place_html


@pytest.mark.parametrize(
    ("source_type", "canonical_ref", "action"),
    [
        ("obsidian", "obsidian://open?vault=Brain&file=note", "Open in Obsidian"),
        ("notion", "https://notion.so/page", "Edit in Notion"),
        ("notion", "https://www.notion.so/page", "Edit in Notion"),
        ("notion", "https://team.notion.so/page", "Edit in Notion"),
    ],
)
def test_item_and_place_allow_only_trusted_canonical_actions(
    source_type, canonical_ref, action
):
    trusted = item(
        "trusted",
        source_type=source_type,
        canonical_ref=canonical_ref,
        cloud_key="food",
        place={"name": "Trusted place"},
    )
    repository = FakeRepository()
    repository.items = [trusted]
    app = create_app(
        dependencies=PortalDependencies(
            repository, TenantResolver(), SearchService(), AnswerService()
        )
    )
    app.config.update(TESTING=True)

    item_html = app.test_client().get("/item/trusted").get_data(as_text=True)
    place_html = app.test_client().get("/place/trusted").get_data(as_text=True)

    assert action in item_html
    assert canonical_ref.replace("&", "&amp;") in item_html
    assert "Open source note" in place_html
    assert canonical_ref.replace("&", "&amp;") in place_html


def test_search_get_filters_change_hits_and_retain_all_filter_state():
    repository = FakeRepository()
    repository.items = [
        item("ai-agent", item_type="method", concepts=("agents",)),
        item(
            "food-place",
            cloud_key="food",
            item_type="place",
            concepts=("restaurants",),
            place={"name": "Quiet noodle shop", "area": "Da'an"},
        ),
        item(
            "old-food",
            cloud_key="food",
            item_type="place",
            concepts=("restaurants",),
            place={"name": "Old cafe"},
            updated_at="2020-01-01T00:00:00+00:00",
        ),
    ]

    def all_hits(tenant_id, query, cloud_key):
        return SearchResults(
            tuple(SearchHit(entry, 1.0, ("lexical",)) for entry in repository.items)
        )

    app = create_app(
        dependencies=PortalDependencies(
            repository, TenantResolver(), all_hits, AnswerService(False)
        )
    )
    app.config.update(TESTING=True)

    response = app.test_client().get(
        "/search?q=food&cloud=food&type=place&concept=restaurants&freshness=7d&place=with_place"
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'method="get"' in html
    for control in ("search-cloud", "search-type", "search-concept", "search-freshness", "search-place"):
        assert f'id="{control}"' in html
    assert '<option value="food" selected>' in html
    assert '<option value="place" selected>' in html
    assert '<option value="restaurants" selected>' in html
    assert '<option value="7d" selected>' in html
    assert '<option value="with_place" selected>' in html
    assert 'data-source-id="food-place"' in html
    assert 'data-source-id="ai-agent"' not in html
    assert 'data-source-id="old-food"' not in html


def test_cloud_filters_are_real_search_links_and_javascript_has_no_dead_toggle(portal_setup):
    client, *_ = portal_setup

    html = client.get("/cloud/ai").get_data(as_text=True)
    javascript = client.get("/portal-static/portal.js").get_data(as_text=True)

    assert '<a class="filter-pill"' in html
    assert 'href="/search?q=Tool&amp;cloud=ai"' in html
    assert "data-filter" not in html
    assert "[data-filter]" not in javascript
    assert 'setAttribute("aria-pressed"' not in javascript


@pytest.mark.parametrize(
    "path",
    ["/", "/search?q=agent", "/cloud/ai", "/item/ai-agent", "/place/food-place", "/sync"],
)
def test_repository_failure_returns_bounded_designed_503(path):
    class FailingRepository:
        def list_items(self, tenant_id):
            raise RuntimeError("private database path and row detail")

    app = create_app(
        dependencies=PortalDependencies(
            FailingRepository(), TenantResolver(), SearchService(), AnswerService()
        )
    )
    app.config.update(TESTING=True)

    response = app.test_client().get(path)
    html = response.get_data(as_text=True)

    assert response.status_code == 503
    assert html.count("<h1") == 1
    assert 'id="service-unavailable"' in html
    assert "Your notes are temporarily unavailable. Try again in a moment." in html
    assert "private database" not in html


def test_item_view_derives_reader_context_and_same_cloud_relations():
    repository = FakeRepository()
    repository.items = [
        item(
            "ai-agent",
            body="First practical point.\n\nSecond supporting point with more detail.",
        ),
        item("related-agent"),
        item("food-place", cloud_key="food", place={"name": "Cafe"}),
    ]
    app = create_app(
        dependencies=PortalDependencies(
            repository, TenantResolver(), SearchService(), AnswerService()
        )
    )
    app.config.update(TESTING=True)

    html = app.test_client().get("/item/ai-agent").get_data(as_text=True)

    assert 'aria-label="Breadcrumb"' in html
    assert "1 min read" in html
    assert "Source-backed" in html
    assert 'id="key-takeaways"' in html
    assert "First practical point." in html
    assert 'id="related-notes"' in html
    assert 'data-source-id="related-agent"' in html
    assert 'data-source-id="food-place"' not in html
    assert "%" not in html


def test_cloud_derives_related_concepts_and_adjacent_clouds(portal_setup):
    client, *_ = portal_setup

    html = client.get("/cloud/ai").get_data(as_text=True)

    assert 'id="related-concepts"' in html
    assert "agents" in html
    assert "reliability" in html
    assert 'id="adjacent-clouds"' in html
    assert 'href="/cloud/food"' in html


def test_place_builds_bounded_encoded_google_maps_search_action():
    repository = FakeRepository()
    repository.items = [
        item(
            "map-place",
            cloud_key="food",
            place={
                "name": "Cafe & Bar" + "N" * 140 + "SECRET_TAIL",
                "address": "1 Main St / Taipei",
            },
        )
    ]
    app = create_app(
        dependencies=PortalDependencies(
            repository, TenantResolver(), SearchService(), AnswerService()
        )
    )
    app.config.update(TESTING=True)

    html = app.test_client().get("/place/map-place").get_data(as_text=True)
    maps_href = re.search(r'href="(https://maps\.google\.com/\?q=[^"]+)"', html)

    assert maps_href is not None
    assert maps_href.group(1).startswith("https://maps.google.com/?q=Cafe+%26+Bar")
    assert "1+Main+St+%2F+Taipei" in maps_href.group(1)
    assert "SECRET_TAIL" not in maps_href.group(1)
    assert "Search in Google Maps" in html


def test_place_without_name_or_address_hides_maps_action():
    repository = FakeRepository()
    repository.items = [item("map-place", cloud_key="food", place={})]
    app = create_app(
        dependencies=PortalDependencies(
            repository, TenantResolver(), SearchService(), AnswerService()
        )
    )
    app.config.update(TESTING=True)

    html = app.test_client().get("/place/map-place").get_data(as_text=True)

    assert "maps.google.com" not in html
    assert "Search in Google Maps" not in html


def test_over_limit_search_query_returns_designed_400_without_services(portal_setup):
    client, _, _, search, answers = portal_setup

    response = client.get("/search?q=" + "q" * 501 + "SECRET_TAIL")
    html = response.get_data(as_text=True)

    assert response.status_code == 400
    assert 'id="query-too-long"' in html
    assert "Keep your search to 500 characters or fewer." in html
    assert 'maxlength="500"' in html
    assert "SECRET_TAIL" not in html
    assert search.calls == []
    assert answers.calls == []
