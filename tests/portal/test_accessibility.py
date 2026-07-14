from __future__ import annotations

from html.parser import HTMLParser

import pytest

from brain_portal.models import CitedAnswer, KnowledgeItem, SearchHit, TenantContext
from brain_portal.search import SearchResults
from brain_portal.web import PortalDependencies
from portal_app import create_app


class StructureParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.h1_count = 0
        self.ids = set()
        self.labels = []
        self.links = []
        self.tags = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.tags.append(tag)
        if tag == "h1":
            self.h1_count += 1
        if "id" in attributes:
            self.ids.add(attributes["id"])
        if tag == "label":
            self.labels.append(attributes.get("for"))
        if tag == "a":
            self.links.append((attributes.get("href"), attributes.get("class", "")))


def portal_item(source_id="ai-agent", cloud="ai", place=None):
    return KnowledgeItem(
        tenant_id="kevin",
        source_id=source_id,
        source_type="obsidian",
        canonical_ref=f"obsidian://{source_id}",
        title="A useful note",
        summary="A concise source-backed summary.",
        body="Body evidence.",
        cloud_key=cloud,
        item_type="research",
        concepts=(),
        place=place,
        source_revision="rev-1",
        updated_at="2026-07-13T10:30:00+00:00",
    )


class Repo:
    def list_items(self, tenant_id):
        return [
            portal_item(),
            portal_item("food-place", "food", {"name": "Place", "area": "Taipei"}),
        ]


def search(tenant_id, query, cloud_key):
    return SearchResults((SearchHit(portal_item(), 1.0, ("lexical",)),))


def answer(query, hits):
    return CitedAnswer("A cited answer.", ("ai-agent",), "gemini")


@pytest.fixture
def accessible_client():
    app = create_app(
        dependencies=PortalDependencies(
            Repo(), lambda: TenantContext("kevin", "Kevin's Brain"), search, answer
        )
    )
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/search?q=agent",
        "/cloud/ai",
        "/item/ai-agent",
        "/place/food-place",
        "/sync",
    ],
)
def test_every_page_has_semantic_shell_skip_link_and_one_h1(accessible_client, path):
    html = accessible_client.get(path).get_data(as_text=True)
    parser = StructureParser()
    parser.feed(html)

    assert html.startswith("<!doctype html>")
    assert '<html lang="zh-Hant">' in html
    assert "header" in parser.tags
    assert "nav" in parser.tags
    assert "main" in parser.tags
    assert parser.h1_count == 1
    assert "main-content" in parser.ids
    assert ("#main-content", "skip-link") in parser.links
    assert "<table" not in html
    assert "—" not in html


def test_search_controls_have_programmatic_labels_and_live_states(accessible_client):
    html = accessible_client.get("/search?q=agent").get_data(as_text=True)
    parser = StructureParser()
    parser.feed(html)

    assert "search-query" in parser.ids
    assert "search-cloud" in parser.ids
    assert "search-query" in parser.labels
    assert "search-cloud" in parser.labels
    assert 'aria-live="polite"' in html
    assert 'data-loading-copy="正在搜尋你的知識庫"' in html


def test_css_encodes_focus_touch_responsive_and_reduced_motion_contracts(accessible_client):
    css = accessible_client.get("/portal-static/portal.css").get_data(as_text=True)

    assert ":focus-visible" in css
    assert "min-height:44px" in css
    assert "--radius:14px" in css
    assert "@media (min-width:760px)" in css
    assert "@media (min-width:1080px)" in css
    assert "prefers-reduced-motion:reduce" in css
    assert "--portal-canvas: #f4f2ed" in css.lower()
    assert "--portal-amber-strong: #c67025" in css.lower()
    assert "--portal-blue: #2f8cff" in css.lower()
    assert "#2f7168" not in css.lower()
    assert "gradient" not in css.lower()


def test_javascript_supports_keyboard_filters_and_loading_feedback(accessible_client):
    javascript = accessible_client.get("/portal-static/portal.js").get_data(as_text=True)

    assert "[data-filter]" not in javascript
    assert 'setAttribute("aria-pressed"' not in javascript
    assert 'setAttribute("aria-busy", "true")' in javascript


def test_wordmark_and_card_primary_links_have_touch_target_contract(accessible_client):
    css = accessible_client.get("/portal-static/portal.css").get_data(as_text=True)

    assert ".wordmark," in css
    assert ".source-card h3 a" in css
    assert "min-height:44px" in css
