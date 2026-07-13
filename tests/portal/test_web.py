from __future__ import annotations

import pytest

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
        body="Evidence, observations, and practical next steps.",
        cloud_key=cloud_key,
        item_type="research",
        concepts=("agents", "reliability"),
        place=place,
        source_revision="rev-1",
        updated_at="2026-07-13T10:30:00+00:00",
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
