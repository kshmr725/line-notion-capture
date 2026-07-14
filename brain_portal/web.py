from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Protocol
from urllib.parse import urlencode, urlparse

from flask import Blueprint, Response, abort, g, render_template, request, url_for

from brain_portal.models import (
    CitedAnswer,
    KnowledgeItem,
    SearchHit,
    SyncRun,
    TenantContext,
)
from brain_portal.answers import QUERY_LIMIT
from brain_portal.briefing import build_briefing
from brain_portal.derived_views import (
    CHART_TYPES,
    CLOUD_TABLE_COLUMNS,
    build_chart,
    build_slides,
    build_table,
    column_choices_for_cloud,
    render_table_csv,
    render_table_markdown,
    serialize_view,
)
from brain_portal.presentation import (
    clean_display_text,
    icon_name_for_cloud,
    icon_name_for_item,
    place_facts,
    public_cloud_label,
    public_type_label,
    reader_overview,
    reader_sections,
    reader_summary,
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
        "description": "用賽道、專案與研究報告，快速看懂 Web3 商業機會。",
        "filters": ("Sector", "Project", "Thesis", "Status"),
        "filter_labels": ("看賽道", "找專案", "讀報告", "看進度"),
        "paths": ("研究一個主題", "比較相鄰專案"),
    },
    {
        "key": "food",
        "name": "美食與咖啡地圖",
        "short_name": "美食地圖",
        "icon_name": "map-pin",
        "description": "用地圖、區域與情境，快速找到想去的店。",
        "filters": ("Area", "Category", "Visit status", "Use case"),
        "filter_labels": ("看地圖", "按類型找", "已去過", "按區域找"),
        "paths": ("找安靜的晚餐", "依區域規劃"),
    },
    {
        "key": "ai",
        "name": "AI 自動化",
        "short_name": "AI 自動化",
        "icon_name": "workflow",
        "description": "用工具、Agent 與工作流，快速重用自動化方法。",
        "filters": ("Tool", "Agent", "MCP", "Workflow", "Reliability"),
        "filter_labels": ("找工具", "找 Agent", "找 MCP", "重用工作流", "看穩定性"),
        "paths": ("建立可靠的 Agent", "用 MCP 串接工具"),
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
        if request.endpoint == "portal.static":
            return
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
        has_filters = any((cloud_key, item_type, concept, freshness, place_filter))
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
            "has_filters": has_filters,
            "filter_summary": _filter_summary(
                cloud_key, item_type, concept, freshness, place_filter
            ),
            "types": sorted({item.item_type for item in items}),
            "type_labels": {
                item.item_type: public_type_label(item.item_type) for item in items
            },
            "concepts": sorted({value for item in items for value in item.concepts}),
        }
        status = 200
        if view["query_too_long"]:
            status = 400
        elif query or has_filters:
            try:
                allowed_items = {item.source_id: item for item in items}
                if query:
                    raw_results = dependencies.search_service(
                        g.portal_tenant.tenant_id,
                        query,
                        cloud_key,
                    )
                    hits = [
                        SearchHit(
                            item=allowed_items[hit.item.source_id],
                            score=hit.score,
                            matched_by=hit.matched_by,
                        )
                        for hit in raw_results.hits
                        if hit.item.source_id in allowed_items
                    ]
                    degraded = raw_results.degraded
                else:
                    hits = [
                        SearchHit(item=entry, score=0.0, matched_by=("filter",))
                        for entry in items
                    ]
                    degraded = False
                hits = _filter_hits(
                    hits, cloud_key, item_type, concept, freshness, place_filter
                )
                if query and has_filters and not hits:
                    fallback_hits = [
                        SearchHit(item=entry, score=0.0, matched_by=("catalog",))
                        for entry in items
                        if _item_matches_query(entry, query)
                    ]
                    hits = _filter_hits(
                        fallback_hits,
                        cloud_key,
                        item_type,
                        concept,
                        freshness,
                        place_filter,
                    )
                answer = (
                    dependencies.answer_service(query, hits)
                    if query and hits
                    else None
                )
                view.update(
                    results=[_item_card(hit.item) for hit in hits],
                    answer=_answer_view(answer, allowed_items),
                    degraded=degraded,
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

    @portal.get("/views/new")
    def view_builder():
        cloud_key = request.args.get("cloud", "").strip()
        cloud_definition = next((c for c in CLOUDS if c["key"] == cloud_key), None)
        if cloud_definition is None or cloud_key not in CLOUD_TABLE_COLUMNS:
            abort(404)
        items = [
            item for item in _tenant_items(dependencies) if item.cloud_key == cloud_key
        ]
        return render_template(
            "portal/view_builder.html",
            page_title=f"轉成表格 · {cloud_definition['name']}",
            tenant=_tenant_view(),
            cloud=cloud_definition,
            columns=column_choices_for_cloud(cloud_key),
            types=sorted({item.item_type for item in items}),
            type_labels={item.item_type: public_type_label(item.item_type) for item in items},
            concepts=sorted({concept for item in items for concept in item.concepts}),
        )

    @portal.get("/views/table")
    def view_table():
        cloud_key = request.args.get("cloud", "").strip()
        cloud_definition = next((c for c in CLOUDS if c["key"] == cloud_key), None)
        if cloud_definition is None or cloud_key not in CLOUD_TABLE_COLUMNS:
            abort(404)
        allowed_columns = {key for key, _ in column_choices_for_cloud(cloud_key)}
        default_columns = [key for key, _ in column_choices_for_cloud(cloud_key)]
        selected_columns = [
            column for column in request.args.getlist("column") if column in allowed_columns
        ] or default_columns
        item_type = request.args.get("type", "").strip()
        concept = request.args.get("concept", "").strip()
        filters = {"cloud": cloud_key}
        if item_type:
            filters["type"] = item_type
        if concept:
            filters["concept"] = concept
        items = _tenant_items(dependencies)
        table = build_table(items, selected_columns, filters)

        export_format = request.args.get("format", "").strip()
        if export_format == "csv":
            return Response(
                render_table_csv(table),
                mimetype="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename={cloud_key}-table.csv"
                },
            )
        if export_format == "markdown":
            return Response(render_table_markdown(table), mimetype="text/markdown")

        export_args = dict(cloud=cloud_key, column=selected_columns)
        if item_type:
            export_args["type"] = item_type
        if concept:
            export_args["concept"] = concept
        return render_template(
            "portal/table_view.html",
            page_title=f"{cloud_definition['name']} 表格",
            tenant=_tenant_view(),
            cloud=cloud_definition,
            table=table,
            all_columns=column_choices_for_cloud(cloud_key),
            selected_columns=selected_columns,
            item_type=item_type,
            concept=concept,
            view_config=serialize_view(table.view),
            csv_url=url_for("portal.view_table", format="csv", **export_args),
            markdown_url=url_for("portal.view_table", format="markdown", **export_args),
            chart_url=url_for(
                "portal.view_chart", cloud=cloud_key, column=selected_columns[0]
            ),
        )

    @portal.get("/views/chart")
    def view_chart():
        cloud_key = request.args.get("cloud", "").strip()
        cloud_definition = next((c for c in CLOUDS if c["key"] == cloud_key), None)
        if cloud_definition is None or cloud_key not in CLOUD_TABLE_COLUMNS:
            abort(404)
        allowed_columns = {key for key, _ in column_choices_for_cloud(cloud_key)}
        default_column = column_choices_for_cloud(cloud_key)[0][0]
        column = request.args.get("column", "").strip()
        if column not in allowed_columns:
            column = default_column
        chart_type = request.args.get("chart_type", "bar").strip()
        if chart_type not in CHART_TYPES:
            chart_type = "bar"
        item_type = request.args.get("type", "").strip()
        concept = request.args.get("concept", "").strip()
        filters = {"cloud": cloud_key}
        if item_type:
            filters["type"] = item_type
        if concept:
            filters["concept"] = concept
        items = _tenant_items(dependencies)
        table = build_table(items, (column,), filters)
        chart = build_chart(table, chart_type)
        max_value = max(chart.values) if chart.values else 0.0
        total_value = sum(chart.values) if chart.values else 0.0
        chart_rows = []
        cumulative_share = 0.0
        for index, (label, value) in enumerate(zip(chart.labels, chart.values)):
            share = round((value / total_value) * 100, 2) if total_value else 0.0
            chart_rows.append(
                {
                    "label": label,
                    "value": value,
                    "percent": round((value / max_value) * 100, 2) if max_value else 0,
                    "share": share,
                    "offset": round(25 - cumulative_share, 2),
                    "color_index": index % 4,
                }
            )
            cumulative_share += share
        return render_template(
            "portal/chart_view.html",
            page_title=f"{cloud_definition['name']} 圖表",
            tenant=_tenant_view(),
            cloud=cloud_definition,
            chart=chart,
            chart_rows=chart_rows,
            column=column,
            column_choices=column_choices_for_cloud(cloud_key),
            chart_type=chart_type,
        )

    @portal.get("/views/slides")
    def view_slides():
        cloud_key = request.args.get("cloud", "").strip()
        cloud_definition = next((c for c in CLOUDS if c["key"] == cloud_key), None)
        if cloud_definition is None or cloud_key not in CLOUD_TABLE_COLUMNS:
            abort(404)
        allowed_columns = {key for key, _ in column_choices_for_cloud(cloud_key)}
        default_columns = [key for key, _ in column_choices_for_cloud(cloud_key)]
        selected_columns = [
            column
            for column in request.args.getlist("column")
            if column in allowed_columns
        ] or default_columns
        item_type = request.args.get("type", "").strip()
        concept = request.args.get("concept", "").strip()
        filters = {"cloud": cloud_key}
        if item_type:
            filters["type"] = item_type
        if concept:
            filters["concept"] = concept
        items = _tenant_items(dependencies)
        table = build_table(items, selected_columns, filters)
        slides = build_slides(table, f"{cloud_definition['name']}簡報")
        source_titles = {
            item.source_id: item.title
            for item in items
            if item.tenant_id == g.portal_tenant.tenant_id
        }
        view_args = {"cloud": cloud_key, "column": selected_columns}
        if item_type:
            view_args["type"] = item_type
        if concept:
            view_args["concept"] = concept
        return render_template(
            "portal/slides_view.html",
            page_title=f"{cloud_definition['name']}簡報",
            tenant=_tenant_view(),
            cloud=cloud_definition,
            slides=slides,
            source_titles=source_titles,
            table_url=url_for("portal.view_table", **view_args),
            chart_url=url_for("portal.view_chart", cloud=cloud_key, column=selected_columns[0]),
            source_count=len(table.rows),
        )

    @portal.get("/views/briefing")
    def view_briefing():
        cloud_key = request.args.get("cloud", "").strip() or None
        if cloud_key and not any(cloud["key"] == cloud_key for cloud in CLOUDS):
            abort(404)
        query = request.args.get("q", "").strip()[:QUERY_LIMIT]
        items = _tenant_items(dependencies)
        allowed_items = {
            item.source_id: item
            for item in items
            if cloud_key is None or item.cloud_key == cloud_key
        }
        answer = None
        if query:
            try:
                raw_results = dependencies.search_service(
                    g.portal_tenant.tenant_id, query, cloud_key
                )
                hits = tuple(
                    SearchHit(
                        item=allowed_items[hit.item.source_id],
                        score=hit.score,
                        matched_by=hit.matched_by,
                    )
                    for hit in raw_results.hits
                    if hit.item.source_id in allowed_items
                )
                answer = dependencies.answer_service(query, list(hits)) if hits else None
            except Exception:
                raise PortalDataUnavailable() from None
        else:
            hits = tuple(
                SearchHit(item=item, score=0.0, matched_by=("catalog",))
                for item in allowed_items.values()
            )
        briefing = build_briefing(query or "這個 Cloud", hits, answer)
        source_titles = {item.source_id: item.title for item in allowed_items.values()}
        cloud_definition = next(
            (cloud for cloud in CLOUDS if cloud["key"] == cloud_key), None
        )
        return render_template(
            "portal/briefing_view.html",
            page_title="來源引用摘要",
            tenant=_tenant_view(),
            briefing=briefing,
            source_titles=source_titles,
            cloud=cloud_definition,
            query=query,
            source_count=len(hits),
            table_url=(
                url_for("portal.view_table", cloud=cloud_key)
                if cloud_key
                else url_for("portal.search")
            ),
            chart_url=(
                url_for("portal.view_chart", cloud=cloud_key)
                if cloud_key
                else url_for("portal.search")
            ),
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
        "display_summary": reader_summary(item.summary, facts),
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
    overview = reader_overview(item.summary, item.body)
    sections = reader_sections(item.body, overview=overview)
    detail.update(
        body=item.body,
        rendered_body=render_markdown_body(item.body),
        concepts=item.concepts,
        place=item.place,
        place_facts=place_facts(item.place, item.summary, item.body),
        canonical_action=_canonical_action(item),
        reading_time=max(1, math.ceil(len(re.findall(r"\w+", item.body)) / 200)),
        confidence="Source-backed",
        reader_overview=overview,
        reader_sections=sections,
        takeaways=[section["body"] for section in sections] or _takeaways(item),
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
        "label": "在 Google 地圖查看",
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


def _item_matches_query(item: KnowledgeItem, query: str) -> bool:
    needle = clean_display_text(query).casefold()
    if not needle:
        return False
    values = [item.title, item.summary, item.body, *item.concepts]
    if item.place:
        values.extend(
            str(value)
            for value in item.place.values()
            if isinstance(value, (str, int, float))
        )
    haystack = clean_display_text(" ".join(values)).casefold()
    return needle in haystack


def _filter_summary(
    cloud_key: str | None,
    item_type: str | None,
    concept: str | None,
    freshness: str | None,
    place_filter: str | None,
) -> str:
    values = []
    if cloud_key:
        values.append(public_cloud_label(cloud_key))
    if item_type:
        values.append(public_type_label(item_type))
    if concept:
        values.append(concept)
    if freshness:
        values.append("最近 7 天" if freshness == "7d" else "最近 30 天")
    if place_filter == "with_place":
        values.append("有地點資料")
    return " · ".join(values)


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
