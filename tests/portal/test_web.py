from __future__ import annotations

import re

import pytest

import portal_app
from brain_portal.config import PortalSettings
from brain_portal.models import (
    CitedAnswer,
    KnowledgeItem,
    SearchHit,
    SyncRun,
    TenantContext,
)
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
    summary: str = "A source-backed summary for this note.",
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
        summary=summary,
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
        self.sync_by_type = {}

    def list_items(self, tenant_id: str):
        self.tenant_calls.append(tenant_id)
        return list(self.items)

    def latest_sync(self, tenant_id: str, source_type: str | None = None):
        return self.sync_by_type.get(source_type)


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


def test_home_leads_with_global_search_then_clouds_then_recent(portal_setup):
    client, *_ = portal_setup

    html = client.get("/").get_data(as_text=True)

    assert html.index('id="global-search"') < html.index('id="cloud-gallery"')
    assert html.index('id="cloud-gallery"') < html.index('id="recent-notes"')
    assert "Knowledge Items" not in html
    assert "從你想找的事開始。" in html


def test_home_is_a_compact_cloud_workbench_with_real_counts(portal_setup):
    client, *_ = portal_setup

    html = client.get("/").get_data(as_text=True)

    assert 'class="workspace-shell"' in html
    assert 'id="cloud-rail"' in html
    assert 'id="global-search"' in html
    assert html.index('id="global-search"') < html.index('id="cloud-gallery"')
    assert "我的 Cloud" in html
    assert 'data-cloud-key="ai"' in html
    assert "3 筆" in html
    assert "尚未索引" in html
    assert 'class="continue-list"' in html
    assert "Find a useful note, then follow its sources." not in html


def test_cloud_gallery_header_opens_an_input_ready_search(portal_setup):
    client, *_ = portal_setup

    html = client.get("/").get_data(as_text=True)

    assert 'class="section-action"' in html
    assert 'href="/search"' in html
    assert "搜尋所有內容" in html


def test_home_uses_semantic_svg_cloud_icons_and_real_previews(portal_setup):
    client, *_ = portal_setup

    html = client.get("/").get_data(as_text=True)

    assert 'data-icon="orbit"' in html
    assert 'data-icon="map-pin"' in html
    assert "◌" not in html and "⌖" not in html and "✦" not in html
    assert "研究一個主題" in html


def test_home_hero_prioritizes_title_and_action_cards(portal_setup):
    client, *_ = portal_setup

    html = client.get("/").get_data(as_text=True)

    assert 'class="workspace-heading home-hero"' in html
    assert html.index("從你想找的事開始") < html.index('class="intent-links"')
    assert 'data-intent="research"' in html
    assert 'data-intent="place"' in html
    assert 'data-intent="method"' in html
    assert 'data-intent="related"' in html
    assert "你的 Second Brain" not in html
    assert "Second Brain · Kevin&#39;s Brain" in html


def test_public_cloud_copy_is_localized_and_consistent_across_home_and_workspace(
    portal_setup,
):
    client, *_ = portal_setup

    home = client.get("/").get_data(as_text=True)
    web3 = client.get("/cloud/web3").get_data(as_text=True)
    food = client.get("/cloud/food").get_data(as_text=True)
    ai = client.get("/cloud/ai").get_data(as_text=True)

    assert "用賽道、專案與研究報告，快速看懂 Web3 商業機會。" in home
    assert "用賽道、專案與研究報告，快速看懂 Web3 商業機會。" in web3
    assert "用地圖、區域與情境，快速找到想去的店。" in home
    assert "用地圖、區域與情境，快速找到想去的店。" in food
    assert "用工具、Agent 與工作流，快速重用自動化方法。" in home
    assert "用工具、Agent 與工作流，快速重用自動化方法。" in ai
    assert "Review an active thesis" not in web3
    assert "Find a quiet dinner" not in food
    assert "Build reliable agents" not in ai
    assert ">AI 自動化</span>" in home


def test_recent_cards_use_reader_facing_summary_for_place_facts():
    repository = FakeRepository()
    repository.items = [
        item(
            "coffee-place",
            cloud_key="food",
            item_type="place",
            place={"name": "Coffee Smoke", "category": "咖啡廳"},
            summary=(
                "⭐ 評價：4.7（Google Maps，643 則） 📍 地址：彰化市永樂街199號 "
                "🕒 時間：13:30–22:00（週四公休） 💰 價位/特色：$200–400／老屋咖啡"
            ),
        )
    ]
    app = create_app(
        dependencies=PortalDependencies(
            repository, TenantResolver(), SearchService(), AnswerService(False)
        )
    )
    app.config.update(TESTING=True)

    html = app.test_client().get("/").get_data(as_text=True)

    assert "評價 4.7（Google Maps，643 則） · 地址 彰化市永樂街199號" in html
    assert "⭐" not in html
    assert "📍" not in html
    assert "🕒" not in html
    assert "💰" not in html


def test_warm_token_contract_and_home_card_hierarchy(portal_setup):
    client, *_ = portal_setup

    html = client.get("/").get_data(as_text=True)
    css = client.get("/portal-static/portal.css").get_data(as_text=True).lower()

    assert "--portal-canvas: #f4f2ed" in css
    assert "--portal-amber-strong: #c67025" in css
    assert "--portal-blue: #2f8cff" in css
    assert "#2f7168" not in css
    assert 'class="intent-link"' in html
    assert 'class="cloud-card"' in html


def test_portal_wide_browser_and_search_workbench_contract(portal_setup):
    client, *_ = portal_setup

    css = client.get("/portal-static/portal.css").get_data(as_text=True)
    html = client.get("/search").get_data(as_text=True)

    assert "1680px" in css
    assert "grid-template-columns: minmax(0, 1fr) auto" in css
    assert 'class="search-query-row"' in html
    assert 'class="filter-bar"' in html


def test_cloud_views_use_domain_specific_data_backed_workspaces(portal_setup):
    client, *_ = portal_setup

    web3_html = client.get("/cloud/web3").get_data(as_text=True)
    food_html = client.get("/cloud/food").get_data(as_text=True)
    ai_html = client.get("/cloud/ai").get_data(as_text=True)

    assert 'id="sector-map"' in web3_html
    assert 'href="/search?q=%E7%9C%8B%E8%B3%BD%E9%81%93&amp;cloud=web3"' in web3_html
    assert 'id="food-discovery"' in food_html
    assert "地圖資料不足，改以清單瀏覽" in food_html
    assert 'id="ai-workspace"' in ai_html
    assert "重用工作流" in ai_html


def test_cloud_workspaces_use_semantic_svg_item_icons(portal_setup):
    client, *_ = portal_setup

    html = "".join(
        client.get(path).get_data(as_text=True)
        for path in ("/cloud/web3", "/cloud/food", "/cloud/ai")
    )

    assert 'data-icon="file-text"' in html
    assert 'data-icon="utensils"' in html
    assert 'data-icon="workflow"' in html
    assert "◌" not in html and "⌖" not in html and "✦" not in html


def test_web3_workspace_has_truthful_sector_cards_and_food_has_map_contract():
    repository = FakeRepository()
    repository.items = [
        item("rwa", cloud_key="web3", concepts=("RWA", "Regulation")),
        item("dep-in", cloud_key="web3", concepts=("DePIN",)),
        item(
            "mapped-food",
            cloud_key="food",
            item_type="place",
            place={"name": "Mapped cafe", "latitude": 25.03, "longitude": 121.54},
        ),
        item("unmapped-food", cloud_key="food", item_type="place", place={"name": "Waiting cafe"}),
    ]
    app = create_app(
        dependencies=PortalDependencies(
            repository, TenantResolver(), SearchService(), AnswerService(False)
        )
    )
    app.config.update(TESTING=True)
    client = app.test_client()

    web3 = client.get("/cloud/web3").get_data(as_text=True)
    food = client.get("/cloud/food").get_data(as_text=True)

    assert 'class="sector-card"' in web3
    assert 'data-sector-count="1"' in web3
    assert 'id="food-map"' in food
    assert 'data-map-points=' in food
    assert "1 可定位 / 1 待補位置" in food
    assert "待補位置" in food


def test_food_map_loads_leaflet_and_has_keyboard_selectable_place_rows():
    repository = FakeRepository()
    repository.items = [
        item(
            "mapped-food",
            cloud_key="food",
            item_type="place",
            place={"name": "Mapped cafe", "latitude": 25.03, "longitude": 121.54},
        )
    ]
    app = create_app(
        dependencies=PortalDependencies(
            repository, TenantResolver(), SearchService(), AnswerService(False)
        )
    )
    app.config.update(TESTING=True)
    client = app.test_client()

    html = client.get("/cloud/food").get_data(as_text=True)
    javascript = client.get("/portal-static/portal.js").get_data(as_text=True)
    css = client.get("/portal-static/portal.css").get_data(as_text=True)

    assert "leaflet.css" in html
    assert "unpkg.com/leaflet@1.9.4" in html
    assert "initFoodMap" in javascript
    assert "brain-cloud:place-selected" in javascript
    assert 'data-place-source-id="mapped-food"' in html
    assert "height:clamp(360px,52vh,560px)" in css
    assert 'querySelectorAll(".map-marker")' in javascript
    assert "scrollWheelZoom: true" in javascript


def test_food_map_has_reader_preview_contract_for_selected_place(portal_setup):
    repository = FakeRepository()
    repository.items = [
        item(
            "mapped-food",
            cloud_key="food",
            item_type="place",
            place={"name": "Mapped cafe", "latitude": 25.03, "longitude": 121.54},
        )
    ]
    app = create_app(
        dependencies=PortalDependencies(
            repository, TenantResolver(), SearchService(), AnswerService(False)
        )
    )
    app.config.update(TESTING=True)
    client = app.test_client()

    html = client.get("/cloud/food").get_data(as_text=True)
    javascript = client.get("/portal-static/portal.js").get_data(as_text=True)

    assert 'id="place-preview"' in html
    assert "點地圖上的地標" in html
    assert "renderPlacePreview" in javascript
    assert "place-preview" in javascript


def test_place_detail_card_prefers_reader_facts_and_hides_coordinates():
    repository = FakeRepository()
    repository.items = [
        item(
            "coffee-place",
            cloud_key="food",
            item_type="place",
            place={
                "name": "咖啡煙（無預約服務）",
                "category": "咖啡廳",
                "latitude": 24.0772181,
                "longitude": 120.5390055,
            },
            summary=(
                "⭐ 評價：4.7（Google Maps，643 則） 📍 地址：彰化市永樂街199號 "
                "🕒 時間：13:30–22:00（週四公休） 💰 價位/特色：$200–400／老屋咖啡、甜點、無預約服務"
            ),
        )
    ]
    app = create_app(
        dependencies=PortalDependencies(
            repository, TenantResolver(), SearchService(), AnswerService(False)
        )
    )
    app.config.update(TESTING=True)

    html = app.test_client().get("/place/coffee-place").get_data(as_text=True)

    assert "評價" in html and "4.7" in html
    assert "彰化市永樂街199號" in html
    assert "13:30–22:00" in html
    assert "$200–400" in html and "老屋咖啡" in html
    assert "Latitude" not in html and "Longitude" not in html
    assert "24.0772181" not in html and "120.5390055" not in html


def test_reader_cards_strip_source_markup_from_summaries():
    repository = FakeRepository()
    repository.items = [
        item("markup", body="**Evidence**", cloud_key="ai")
    ]
    repository.items[0] = KnowledgeItem(
        **{
            **repository.items[0].__dict__,
            "summary": "Useful **summary**<br>with a [[MCP|model protocol]] link #agent",
        }
    )
    app = create_app(
        dependencies=PortalDependencies(
            repository, TenantResolver(), SearchService(), AnswerService(False)
        )
    )
    app.config.update(TESTING=True)

    html = app.test_client().get("/").get_data(as_text=True)

    assert "Useful summary with a model protocol link agent" in html
    assert "<br>" not in html
    assert "**summary**" not in html
    assert "[[MCP" not in html
    assert "#agent" not in html


def test_item_reader_renders_markdown_body_without_source_syntax():
    repository = FakeRepository()
    repository.items = [
        item(
            "formatted",
            body="# 不應該露出的 Markdown 標記\n\n**重點**<br>第二行\n\n- 第一項\n- 第二項",
        )
    ]
    app = create_app(
        dependencies=PortalDependencies(
            repository, TenantResolver(), SearchService(), AnswerService(False)
        )
    )
    app.config.update(TESTING=True)

    html = app.test_client().get("/item/formatted").get_data(as_text=True)

    assert "<h2>不應該露出的 Markdown 標記</h2>" in html
    assert "<strong>重點</strong><br>第二行" in html
    assert "<ul>" in html and "<li>第一項</li>" in html
    assert "# 不應該露出的 Markdown 標記" not in html


def test_workspace_navigation_uses_task_language_instead_of_schema_terms(portal_setup):
    client, *_ = portal_setup

    home = client.get("/").get_data(as_text=True)
    web3 = client.get("/cloud/web3").get_data(as_text=True)
    food = client.get("/cloud/food").get_data(as_text=True)
    ai = client.get("/cloud/ai").get_data(as_text=True)

    assert 'data-nav-group="clouds"' in home
    assert "看賽道" in web3 and "找專案" in web3 and "讀報告" in web3
    assert "附近想去" in food and "按區域找" in food
    assert "找工具" in ai and "重用工作流" in ai
    assert "Sector" not in web3 and "Project" not in web3 and "Thesis" not in web3
    assert 'id="related-concepts"' not in web3


def test_public_item_labels_hide_internal_type_keys(portal_setup):
    client, *_ = portal_setup

    html = client.get("/cloud/ai").get_data(as_text=True)

    assert "研究筆記" in html
    assert "research ·" not in html


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
    assert "目前以關鍵字結果為主；語意搜尋恢復後會自動加入。" in html
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
    assert "目前無法生成有充分證據支持的回答；請先閱讀下方來源。" in html
    assert 'data-source-id="ai-agent"' in html


def test_blank_search_has_empty_state_and_does_not_call_services(portal_setup):
    client, _, _, search, answers = portal_setup

    html = client.get("/search").get_data(as_text=True)

    assert 'id="search-empty-state"' in html
    assert "你也可以先選一個入口，系統會保留最接近的原始筆記供你確認。" in html
    assert search.calls == []
    assert answers.calls == []


def test_search_controls_separate_primary_query_from_optional_filters(portal_setup):
    client, *_ = portal_setup

    html = client.get("/search").get_data(as_text=True)

    assert 'class="search-query-row"' in html
    assert 'class="filter-primary"' in html
    assert 'class="filter-advanced"' in html
    assert "更多篩選" in html
    assert 'href="/search"' in html
    assert "清除篩選" in html


def test_search_filters_work_without_a_query(portal_setup):
    client, _, _, search, answers = portal_setup

    html = client.get("/search?cloud=food").get_data(as_text=True)

    assert 'id="search-filter-summary"' in html
    assert "美食地圖" in html
    assert 'id="search-empty-state"' not in html
    assert 'data-source-id="food-place"' in html
    assert 'data-source-id="ai-agent"' not in html
    assert search.calls == []
    assert answers.calls == []


def test_search_filter_falls_back_to_catalog_when_ranked_hits_miss_scope():
    repository = FakeRepository()
    repository.items = [
        item(
            "food-place",
            cloud_key="food",
            item_type="place",
            place={"name": "Quiet coffee shop"},
            summary="A quiet coffee shop for focused work.",
        ),
        item("ai-agent", cloud_key="ai", summary="An unrelated automation note."),
    ]

    def misses_food_scope(tenant_id, query, cloud_key):
        return SearchResults((SearchHit(repository.items[1], 1.0, ("lexical",)),))

    app = create_app(
        dependencies=PortalDependencies(
            repository, TenantResolver(), misses_food_scope, AnswerService(False)
        )
    )
    app.config.update(TESTING=True)

    html = app.test_client().get("/search?q=coffee&cloud=food").get_data(as_text=True)

    assert 'data-source-id="food-place"' in html
    assert 'data-source-id="ai-agent"' not in html


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
    assert "請稍候再試；你的原始資料不會因此被修改。" in html
    assert "private provider detail" not in html


def test_item_is_answer_first_and_has_obsidian_action(portal_setup):
    client, *_ = portal_setup

    html = client.get("/item/ai-agent").get_data(as_text=True)

    assert html.index('id="item-answer"') < html.index('id="item-metadata"')
    assert "在 Obsidian 開啟" in html
    assert 'href="obsidian://open?vault=Brain&amp;file=ai-agent"' in html


def test_notion_item_has_direct_edit_action(portal_setup):
    client, *_ = portal_setup

    html = client.get("/item/notion-page").get_data(as_text=True)

    assert "在 Notion 編輯" in html
    assert 'href="https://www.notion.so/notion-page"' in html


def test_cloud_has_domain_filters_and_featured_paths(portal_setup):
    client, *_ = portal_setup

    html = client.get("/cloud/ai").get_data(as_text=True)

    assert 'id="cloud-filters"' in html
    assert "找工具" in html
    assert "重用工作流" in html
    assert 'id="featured-paths"' in html
    assert "建立可靠的 Agent" in html
    assert 'data-source-id="ai-agent"' in html


def test_place_and_sync_pages_use_reader_facing_states(portal_setup):
    client, *_ = portal_setup

    place_html = client.get("/place/food-place").get_data(as_text=True)
    sync_html = client.get("/sync").get_data(as_text=True)

    assert "Da&#39;an" in place_html
    assert "查看原始筆記" in place_html
    assert 'id="sync-status"' in sync_html
    assert "尚未索引" in sync_html


def test_sync_page_surfaces_a_stale_source_state(portal_setup):
    client, repository, *_ = portal_setup
    repository.sync_by_type[None] = SyncRun("obsidian", "stale", "2026-07-13T10:30:00+00:00")

    html = client.get("/sync").get_data(as_text=True)

    assert "需要更新" in html
    assert "已是最新" not in html


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
    assert "在 Obsidian 開啟" not in item_html
    assert "在 Notion 編輯" not in item_html
    assert "Open source note" not in place_html


@pytest.mark.parametrize(
    ("source_type", "canonical_ref", "action"),
    [
        ("obsidian", "obsidian://open?vault=Brain&file=note", "在 Obsidian 開啟"),
        ("notion", "https://notion.so/page", "在 Notion 編輯"),
        ("notion", "https://www.notion.so/page", "在 Notion 編輯"),
        ("notion", "https://team.notion.so/page", "在 Notion 編輯"),
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
    assert "查看原始筆記" in place_html
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
    assert 'href="/search?q=%E6%89%BE%E5%B7%A5%E5%85%B7&amp;cloud=ai"' in html
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
    assert "請稍候再試；原始 Obsidian 或 Notion 內容不會被修改。" in html
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
    assert "1 分鐘閱讀" in html
    assert "原始來源支援" in html
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
    assert 'id="cloud-rail"' in html
    assert 'href="/cloud/food"' in html


def test_cloud_concept_links_can_cross_cloud_boundaries():
    repository = FakeRepository()
    repository.items = [
        item("ai-agent", cloud_key="ai", concepts=("agents",)),
        item("web3-agent", cloud_key="web3", concepts=("agents",)),
    ]
    app = create_app(
        dependencies=PortalDependencies(
            repository, TenantResolver(), SearchService(), AnswerService()
        )
    )
    app.config.update(TESTING=True)

    html = app.test_client().get("/cloud/ai").get_data(as_text=True)

    assert 'href="/search?q=agents&amp;concept=agents"' in html
    assert 'cloud=ai&amp;' not in html


def test_food_workspace_renders_only_real_coordinate_map_markers():
    repository = FakeRepository()
    repository.items = [
        item(
            "food-place",
            cloud_key="food",
            place={"name": "Quiet noodle shop", "latitude": 25.03, "longitude": 121.54},
        )
    ]
    app = create_app(
        dependencies=PortalDependencies(
            repository, TenantResolver(), SearchService(), AnswerService()
        )
    )
    app.config.update(TESTING=True)

    html = app.test_client().get("/cloud/food").get_data(as_text=True)

    assert 'id="food-map"' in html
    assert 'data-source-id="food-place"' in html
    assert 'data-latitude="25.03"' in html
    assert "1 可定位 / 0 待補位置" in html
    assert "地圖資料不足" not in html


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
    assert "在 Google 地圖查看" in html


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
    assert "在 Google 地圖查看" not in html


def test_over_limit_search_query_returns_designed_400_without_services(portal_setup):
    client, _, _, search, answers = portal_setup

    response = client.get("/search?q=" + "q" * 501 + "SECRET_TAIL")
    html = response.get_data(as_text=True)

    assert response.status_code == 400
    assert 'id="query-too-long"' in html
    assert "請將搜尋文字控制在 500 個字元以內。" in html
    assert 'maxlength="500"' in html
    assert "SECRET_TAIL" not in html
    assert search.calls == []
    assert answers.calls == []


@pytest.mark.parametrize(
    ("status", "label"),
    [
        ("running", "索引中"),
        ("success", "已是最新"),
        ("stale", "需要更新"),
        ("permission_required", "需要重新授權"),
    ],
)
def test_item_shows_derived_sync_status_label(portal_setup, status, label):
    client, repository, *_ = portal_setup
    repository.sync_by_type["obsidian"] = SyncRun(
        source_type="obsidian", status=status, finished_at="2026-07-13T12:00:00+00:00"
    )

    html = client.get("/item/ai-agent").get_data(as_text=True)

    assert label in html


def test_item_hides_sync_status_badge_when_no_sync_recorded(portal_setup):
    client, *_ = portal_setup

    html = client.get("/item/ai-agent").get_data(as_text=True)

    assert "索引中" not in html
    assert "已是最新" not in html
    assert "需要更新" not in html
    assert "需要重新授權" not in html


def test_item_returns_bounded_503_when_sync_status_lookup_fails():
    class FailingSyncRepository(FakeRepository):
        def latest_sync(self, tenant_id, source_type=None):
            raise RuntimeError("private database path and row detail")

    app = create_app(
        dependencies=PortalDependencies(
            FailingSyncRepository(), TenantResolver(), SearchService(), AnswerService()
        )
    )
    app.config.update(TESTING=True)

    response = app.test_client().get("/item/ai-agent")
    html = response.get_data(as_text=True)

    assert response.status_code == 503
    assert 'id="service-unavailable"' in html
    assert "private database" not in html
