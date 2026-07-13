from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol
from urllib.parse import urlparse

from flask import Blueprint, abort, g, render_template, request, url_for

from brain_portal.models import CitedAnswer, KnowledgeItem, SearchHit, TenantContext
from brain_portal.search import SearchResults


class ItemRepository(Protocol):
    def list_items(self, tenant_id: str) -> list[KnowledgeItem]:
        ...


TenantResolver = Callable[[], Optional[TenantContext]]
SearchService = Callable[[str, str, Optional[str]], SearchResults]
AnswerService = Callable[[str, list[SearchHit]], Optional[CitedAnswer]]


@dataclass(frozen=True)
class PortalDependencies:
    repository: ItemRepository
    tenant_resolver: TenantResolver
    search_service: SearchService
    answer_service: AnswerService


CLOUDS = (
    {
        "key": "ai",
        "name": "AI Automation",
        "description": "Methods, tools, and reliable agent workflows.",
        "filters": ("Tool", "Agent", "Workflow", "Reliability"),
        "paths": (
            "Build reliable agents",
            "Connect tools with MCP",
            "Reuse an automation method",
        ),
    },
    {
        "key": "web3",
        "name": "Web3 Research",
        "description": "Projects, markets, and investment theses in context.",
        "filters": ("Sector", "Project", "Thesis", "Status"),
        "paths": (
            "Review an active thesis",
            "Compare adjacent projects",
            "Trace a market signal",
        ),
    },
    {
        "key": "food",
        "name": "Food and Places",
        "description": "Restaurants and field notes organized for real decisions.",
        "filters": ("Area", "Category", "Visit status", "Use case"),
        "paths": (
            "Find a quiet dinner",
            "Return to a favorite place",
            "Plan by neighborhood",
        ),
    },
)


def create_portal_blueprint(dependencies: PortalDependencies) -> Blueprint:
    portal = Blueprint(
        "portal",
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/portal-static",
    )

    @portal.before_request
    def resolve_request_tenant():
        tenant = dependencies.tenant_resolver()
        if tenant is None or not tenant.tenant_id.strip():
            abort(401)
        g.portal_tenant = tenant

    @portal.get("/")
    def home():
        items = _tenant_items(dependencies)
        return render_template(
            "portal/home.html",
            page_title="Home",
            tenant=_tenant_view(),
            clouds=CLOUDS,
            recent=[_item_card(item) for item in items[:6]],
        )

    @portal.get("/search")
    def search():
        items = _tenant_items(dependencies)
        query = request.args.get("q", "").strip()
        cloud_key = request.args.get("cloud", "").strip() or None
        view = {
            "query": query,
            "cloud_key": cloud_key,
            "clouds": CLOUDS,
            "results": [],
            "answer": None,
            "degraded": False,
            "error": False,
        }
        status = 200
        if query:
            try:
                raw_results = dependencies.search_service(
                    g.portal_tenant.tenant_id,
                    query,
                    cloud_key,
                )
                allowed_items = {item.source_id: item for item in items}
                hits = [
                    SearchHit(
                        item=allowed_items[hit.item.source_id],
                        score=hit.score,
                        matched_by=hit.matched_by,
                    )
                    for hit in raw_results.hits
                    if hit.item.source_id in allowed_items
                ]
                answer = dependencies.answer_service(query, hits) if hits else None
                view.update(
                    results=[_item_card(hit.item) for hit in hits],
                    answer=_answer_view(answer, allowed_items),
                    degraded=raw_results.degraded,
                )
            except Exception:
                view["error"] = True
                status = 503
        return (
            render_template(
                "portal/search.html",
                page_title="Search",
                tenant=_tenant_view(),
                view=view,
            ),
            status,
        )

    @portal.get("/cloud/<key>")
    def cloud(key: str):
        cloud_view = next((cloud for cloud in CLOUDS if cloud["key"] == key), None)
        if cloud_view is None:
            abort(404)
        items = [item for item in _tenant_items(dependencies) if item.cloud_key == key]
        return render_template(
            "portal/cloud.html",
            page_title=cloud_view["name"],
            tenant=_tenant_view(),
            cloud=cloud_view,
            items=[_item_card(item) for item in items],
        )

    @portal.get("/item/<path:source_id>")
    def item_detail(source_id: str):
        item = _find_item(_tenant_items(dependencies), source_id)
        if item is None:
            abort(404)
        return render_template(
            "portal/item.html",
            page_title=item.title,
            tenant=_tenant_view(),
            item=_item_detail(item),
        )

    @portal.get("/place/<path:source_id>")
    def place_detail(source_id: str):
        item = _find_item(_tenant_items(dependencies), source_id)
        if item is None or item.place is None:
            abort(404)
        return render_template(
            "portal/place.html",
            page_title=item.title,
            tenant=_tenant_view(),
            item=_item_detail(item),
        )

    @portal.get("/sync")
    def sync():
        items = _tenant_items(dependencies)
        last_updated = max((item.updated_at for item in items), default=None)
        return render_template(
            "portal/sync.html",
            page_title="Source status",
            tenant=_tenant_view(),
            sync={
                "state": "Up to date",
                "last_updated": last_updated,
                "source_count": len(items),
            },
        )

    return portal


def _tenant_items(dependencies: PortalDependencies) -> list[KnowledgeItem]:
    tenant_id = g.portal_tenant.tenant_id
    return [
        item
        for item in dependencies.repository.list_items(tenant_id)
        if item.tenant_id == tenant_id
    ]


def _find_item(items: list[KnowledgeItem], source_id: str) -> KnowledgeItem | None:
    return next((item for item in items if item.source_id == source_id), None)


def _tenant_view() -> dict[str, str]:
    return {
        "tenant_id": g.portal_tenant.tenant_id,
        "display_name": g.portal_tenant.display_name,
    }


def _item_card(item: KnowledgeItem) -> dict[str, object]:
    return {
        "source_id": item.source_id,
        "title": item.title,
        "summary": item.summary,
        "cloud_key": item.cloud_key,
        "item_type": item.item_type,
        "updated_at": item.updated_at,
        "url": url_for("portal.item_detail", source_id=item.source_id),
        "place_url": (
            url_for("portal.place_detail", source_id=item.source_id)
            if item.place is not None
            else None
        ),
    }


def _item_detail(item: KnowledgeItem) -> dict[str, object]:
    detail = _item_card(item)
    detail.update(
        body=item.body,
        concepts=item.concepts,
        place=item.place,
        canonical_action=_canonical_action(item),
    )
    return detail


def _canonical_action(item: KnowledgeItem) -> dict[str, str] | None:
    canonical_ref = item.canonical_ref
    if not canonical_ref or canonical_ref != canonical_ref.strip():
        return None
    parsed = urlparse(canonical_ref)
    if item.source_type == "obsidian" and parsed.scheme.lower() == "obsidian":
        return {"url": canonical_ref, "label": "Open in Obsidian"}
    if item.source_type != "notion" or parsed.scheme.lower() != "https":
        return None
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if hostname != "notion.so" and not hostname.endswith(".notion.so"):
        return None
    return {"url": canonical_ref, "label": "Edit in Notion"}


def _answer_view(
    answer: CitedAnswer | None,
    allowed_items: dict[str, KnowledgeItem],
) -> dict[str, object] | None:
    if answer is None:
        return None
    citations = [
        {
            "source_id": source_id,
            "title": allowed_items[source_id].title,
            "url": url_for("portal.item_detail", source_id=source_id),
        }
        for source_id in answer.source_ids
        if source_id in allowed_items
    ]
    if not citations:
        return None
    return {"text": answer.text, "citations": citations, "provider": answer.provider}
