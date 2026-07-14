from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Protocol
from urllib.parse import urlencode, urlparse

from flask import Blueprint, abort, g, render_template, request, url_for

from brain_portal.models import (
    CitedAnswer,
    KnowledgeItem,
    SearchHit,
    SyncRun,
    TenantContext,
)
from brain_portal.answers import QUERY_LIMIT
from brain_portal.presentation import (
    clean_display_text,
    icon_name_for_cloud,
    icon_name_for_item,
    place_facts,
    public_cloud_label,
    public_type_label,
    render_markdown_body,
)
from brain_portal.search import SearchResults


SYNC_STATUS_LABELS = {
    "running": "索引中",
    "success": "已是最新",
    "stale": "需要更新",
    "permission_required": "需要重新授權",
}


class ItemRepository(Protocol):
    def list_items(self, tenant_id: str) -> list[KnowledgeItem]:
        ...

    def latest_sync(
        self, tenant_id: str, source_type: str | None = None
    ) -> SyncRun | None:
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


class PortalDataUnavailable(Exception):
    pass


CLOUDS = (
    {
        "key": "web3",
        "name": "Web3 商業研究",
        "short_name": "Web3",
        "icon_name": "orbit",
        "description": "賽道、專案與概念 Wiki。",
        "filters": ("Sector", "Project", "Thesis", "Status"),
        "filter_labels": ("賽道總覽", "找專案", "讀研究", "看狀態"),
        "paths": ("Review an active thesis", "Compare adjacent projects"),
    },
    {
        "key": "food",
        "name": "美食與咖啡地圖",
        "short_name": "美食地圖",
        "icon_name": "map-pin",
        "description": "地點、想去清單與使用情境。",
        "filters": ("Area", "Category", "Visit status", "Use case"),
        "filter_labels": ("附近想去", "按類型找", "已去過", "按區域找"),
        "paths": ("Find a quiet dinner", "Plan by neighborhood"),
    },
    {
        "key": "ai",
        "name": "AI 自動化",
        "short_name": "AI 自動化",
        "icon_name": "workflow",
        "description": "工具、Agent 與可重用的工作流。",
        "filters": ("Tool", "Agent", "MCP", "Workflow", "Reliability"),
        "filter_labels": ("找工具", "找 Agent", "找 MCP", "重用工作流", "看穩定性"),
        "paths": ("Build reliable agents", "Connect tools with MCP"),
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

    @portal.context_processor
    def workspace_context():
        active_cloud = None
        if request.endpoint == "portal.cloud":
            active_cloud = request.view_args.get("key") if request.view_args else None
        return {"nav_clouds": CLOUDS, "active_cloud_key": active_cloud}

    @portal.errorhandler(PortalDataUnavailable)
    def service_unavailable(error):
        return (
            render_template(
                "portal/service_unavailable.html",
                page_title="Notes unavailable",
                tenant=_tenant_view(),
            ),
            503,
        )

    @portal.get("/")
    def home():
        items = _tenant_items(dependencies)
        return render_template(
            "portal/home.html",
            page_title="首頁",
            tenant=_tenant_view(),
            clouds=_cloud_cards(items),
            recent=[_item_card(item) for item in items[:6]],
        )

    @portal.get("/search")
    def search():
        items = _tenant_items(dependencies)
        query = request.args.get("q", "").strip()
        cloud_key = request.args.get("cloud", "").strip() or None
        item_type = request.args.get("type", "").strip() or None
        concept = request.args.get("concept", "").strip() or None
        freshness = request.args.get("freshness", "").strip() or None
        place_filter = request.args.get("place", "").strip() or None
        view = {
            "query": query[:QUERY_LIMIT],
            "cloud_key": cloud_key,
            "clouds": CLOUDS,
            "results": [],
            "answer": None,
            "degraded": False,
            "error": False,
            "query_too_long": len(query) > QUERY_LIMIT,
            "item_type": item_type,
            "concept": concept,
            "freshness": freshness,
            "place_filter": place_filter,
            "types": sorted({item.item_type for item in items}),
            "type_labels": {
                item.item_type: public_type_label(item.item_type) for item in items
            },
            "concepts": sorted({value for item in items for value in item.concepts}),
        }
        status = 200
        if view["query_too_long"]:
            status = 400
        elif query:
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
                hits = _filter_hits(
                    hits, cloud_key, item_type, concept, freshness, place_filter
                )
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
            page_title="搜尋",
                tenant=_tenant_view(),
                view=view,
            ),
            status,
        )

    @portal.get("/cloud/<key>")
    def cloud(key: str):
        cloud_definition = next((cloud for cloud in CLOUDS if cloud["key"] == key), None)
        if cloud_definition is None:
            abort(404)
        all_items = _tenant_items(dependencies)
        items = [item for item in all_items if item.cloud_key == key]
        cloud_view = dict(cloud_definition)
        cloud_view["filters"] = [
            {
                "label": display_label,
                "url": url_for("portal.search", q=display_label, cloud=key),
            }
            for display_label in cloud_definition.get(
                "filter_labels", cloud_definition["filters"]
            )
        ]
        concepts = sorted({concept for item in items for concept in item.concepts})
        available_clouds = {item.cloud_key for item in all_items if item.cloud_key != key}
        adjacent = [
            {
                "name": cloud["name"],
                "url": url_for("portal.cloud", key=cloud["key"]),
            }
            for cloud in CLOUDS
            if cloud["key"] in available_clouds
        ]
        return render_template(
            "portal/cloud.html",
            page_title=cloud_view["name"],
            tenant=_tenant_view(),
            cloud=cloud_view,
            items=[_item_card(item) for item in items],
            concepts=concepts,
            adjacent_clouds=adjacent,
            workspace=_cloud_workspace(items, key, all_items),
        )

    @portal.get("/item/<path:source_id>")
    def item_detail(source_id: str):
        items = _tenant_items(dependencies)
        item = _find_item(items, source_id)
        if item is None:
            abort(404)
        detail = _item_detail(item)
        detail["sync_status"] = _sync_status_label(
            dependencies, g.portal_tenant.tenant_id, item
        )
        return render_template(
            "portal/item.html",
            page_title=item.title,
            tenant=_tenant_view(),
            item=detail,
            breadcrumbs=_breadcrumbs(item),
            related=[
                _item_card(candidate)
                for candidate in items
                if candidate.source_id != item.source_id
                and candidate.cloud_key == item.cloud_key
            ][:3],
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
        try:
            latest_sync = dependencies.repository.latest_sync(g.portal_tenant.tenant_id)
        except Exception:
            raise PortalDataUnavailable() from None
        last_updated = (
            latest_sync.finished_at
            if latest_sync is not None and latest_sync.finished_at
            else max((item.updated_at for item in items), default=None)
        )
        return render_template(
            "portal/sync.html",
            page_title="資料來源",
            tenant=_tenant_view(),
            sync={
                "state": (
                    SYNC_STATUS_LABELS.get(latest_sync.status, "需要確認")
                    if latest_sync is not None
                    else "尚未索引"
                ),
                "last_updated": last_updated,
                "source_count": len(items),
            },
        )

    return portal


def _tenant_items(dependencies: PortalDependencies) -> list[KnowledgeItem]:
    tenant_id = g.portal_tenant.tenant_id
    try:
        raw_items = dependencies.repository.list_items(tenant_id)
    except Exception:
        raise PortalDataUnavailable() from None
    return [
        item
        for item in raw_items
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
    facts = place_facts(item.place, item.summary, item.body)
    return {
        "source_id": item.source_id,
        "title": item.title,
        "summary": clean_display_text(item.summary),
        "cloud_key": item.cloud_key,
        "cloud_label": public_cloud_label(item.cloud_key),
        "item_type": item.item_type,
        "item_type_label": public_type_label(item.item_type),
        "icon_name": icon_name_for_item(item),
        "updated_at": item.updated_at,
        "concepts": item.concepts,
        "place": item.place,
        "place_facts": facts,
        "has_coordinates": _place_has_coordinates(item.place),
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
        rendered_body=render_markdown_body(item.body),
        concepts=item.concepts,
        place=item.place,
        place_facts=place_facts(item.place, item.summary, item.body),
        canonical_action=_canonical_action(item),
        reading_time=max(1, math.ceil(len(re.findall(r"\w+", item.body)) / 200)),
        confidence="Source-backed",
        takeaways=_takeaways(item),
        maps_action=_maps_action(item.place),
    )
    return detail


def _sync_status_label(
    dependencies: PortalDependencies, tenant_id: str, item: KnowledgeItem
) -> str | None:
    try:
        sync = dependencies.repository.latest_sync(tenant_id, item.source_type)
    except Exception:
        raise PortalDataUnavailable() from None
    if sync is None:
        return None
    return SYNC_STATUS_LABELS.get(sync.status)


def _breadcrumbs(item: KnowledgeItem) -> list[dict[str, str | None]]:
    cloud = next((cloud for cloud in CLOUDS if cloud["key"] == item.cloud_key), None)
    values = [{"label": "Home", "url": url_for("portal.home")}]
    if cloud is not None:
        values.append(
            {"label": cloud["name"], "url": url_for("portal.cloud", key=item.cloud_key)}
        )
    values.append({"label": item.title, "url": None})
    return values


def _takeaways(item: KnowledgeItem) -> list[str]:
    def clean_takeaway(value: str) -> str:
        text = clean_display_text(value)
        text = re.sub(r"^(?:K#|#{1,6})\s*", "", text)
        return re.sub(r"^(?:[-*]|\d+\.)\s+", "", text).strip()

    values = [clean_takeaway(item.summary)]
    values.extend(
        clean_takeaway(part) for part in item.body.split("\n\n") if part.strip()
    )
    return list(dict.fromkeys(value[:280] for value in values if value))[:3]


def _maps_action(place: dict[str, object] | None) -> dict[str, str] | None:
    if not place:
        return None
    parts = []
    for key in ("name", "address", "area"):
        value = place.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip()[:120])
    if not parts:
        return None
    return {
        "url": "https://maps.google.com/?" + urlencode({"q": " ".join(parts)}),
        "label": "Search in Google Maps",
    }


def _filter_hits(
    hits: list[SearchHit],
    cloud_key: str | None,
    item_type: str | None,
    concept: str | None,
    freshness: str | None,
    place_filter: str | None,
) -> list[SearchHit]:
    cutoff = None
    if freshness in {"7d", "30d"}:
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(freshness[:-1]))
    filtered = []
    for hit in hits:
        item = hit.item
        if cloud_key and item.cloud_key != cloud_key:
            continue
        if item_type and item.item_type != item_type:
            continue
        if concept and concept not in item.concepts:
            continue
        if place_filter == "with_place" and item.place is None:
            continue
        if cutoff is not None:
            try:
                updated_at = datetime.fromisoformat(item.updated_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if updated_at < cutoff:
                continue
        filtered.append(hit)
    return filtered


def _canonical_action(item: KnowledgeItem) -> dict[str, str] | None:
    canonical_ref = item.canonical_ref
    if not canonical_ref or canonical_ref != canonical_ref.strip():
        return None
    parsed = urlparse(canonical_ref)
    if item.source_type == "obsidian" and parsed.scheme.lower() == "obsidian":
        return {
            "url": canonical_ref,
            "label": "在 Obsidian 開啟",
            "legacy_label": "Open in Obsidian",
        }
    if item.source_type != "notion" or parsed.scheme.lower() != "https":
        return None
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if hostname != "notion.so" and not hostname.endswith(".notion.so"):
        return None
    return {
        "url": canonical_ref,
        "label": "在 Notion 編輯",
        "legacy_label": "Edit in Notion",
    }


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


def _cloud_cards(items: list[KnowledgeItem]) -> list[dict[str, object]]:
    cards = []
    for cloud in CLOUDS:
        cloud_items = [item for item in items if item.cloud_key == cloud["key"]]
        card = dict(cloud)
        card.update(
            count=len(cloud_items),
            count_label=f"{len(cloud_items)} 筆" if cloud_items else "尚未索引",
            freshness=_freshness_label(cloud_items),
            icon_name=icon_name_for_cloud(cloud["key"]),
            preview_titles=[item.title for item in cloud_items[:2]],
            url=url_for("portal.cloud", key=cloud["key"]),
        )
        cards.append(card)
    return cards


def _freshness_label(items: list[KnowledgeItem]) -> str:
    if not items:
        return "尚未索引"
    latest = max(item.updated_at for item in items)
    return f"更新於 {latest[:10]}"


def _cloud_workspace(
    items: list[KnowledgeItem], key: str, all_items: list[KnowledgeItem]
) -> dict[str, object]:
    definition = next(cloud for cloud in CLOUDS if cloud["key"] == key)
    filter_labels = definition.get("filter_labels", definition["filters"])
    tabs = [
        {
            "label": display_label,
            "url": url_for("portal.search", q=display_label, cloud=key),
        }
        for display_label in filter_labels
    ]
    concepts = sorted({concept for item in items for concept in item.concepts})
    concept_counts = [
        {
            "label": concept,
            "count": sum(concept in item.concepts for item in items),
            "url": url_for("portal.search", q=concept, concept=concept),
        }
        for concept in concepts
    ]
    sectors = _sector_views(items, key)
    places = [item for item in items if item.place is not None]
    map_points = _map_points(places)
    return {
        "tabs": tabs,
        "recent": [_item_card(item) for item in items[:6]],
        "concepts": concept_counts,
        "sectors": sectors,
        "places": [_item_card(item) for item in places],
        "has_coordinates": bool(map_points),
        "map_points": map_points,
        "coordinate_count": len(map_points),
        "unlocated_count": len(places) - len(map_points),
        "item_count": len(items),
    }


def _sector_views(items: list[KnowledgeItem], key: str) -> list[dict[str, object]]:
    """Project source-backed concepts into clickable Cloud navigation tiles."""
    if key != "web3":
        return []
    counts: dict[str, int] = {}
    for item in items:
        for concept in item.concepts:
            label = str(concept).strip()
            if label:
                counts[label] = counts.get(label, 0) + 1
    return [
        {
            "name": label,
            "count": count,
            "url": url_for("portal.search", q=label, cloud=key),
        }
        for label, count in sorted(counts.items(), key=lambda value: (-value[1], value[0].casefold()))
    ]


def _place_has_coordinates(place: dict[str, object] | None) -> bool:
    if place is None:
        return False
    try:
        latitude = float(place.get("latitude", ""))
        longitude = float(place.get("longitude", ""))
    except (TypeError, ValueError):
        return False
    return math.isfinite(latitude) and math.isfinite(longitude)


def _map_points(items: list[KnowledgeItem]) -> list[dict[str, object]]:
    raw = []
    for item in items:
        if not _place_has_coordinates(item.place):
            continue
        raw.append(
            (
                _item_card(item),
                float(item.place["latitude"]),
                float(item.place["longitude"]),
            )
        )
    if not raw:
        return []
    return [
        {
            "item": card,
            "latitude": latitude,
            "longitude": longitude,
        }
        for card, latitude, longitude in raw
    ]
