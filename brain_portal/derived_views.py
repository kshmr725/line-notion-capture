from __future__ import annotations

import csv
import io
import json
from typing import Callable, Mapping, Sequence

from brain_portal.models import ChartSpec, DerivedTable, DerivedView, KnowledgeItem, TableRow
from brain_portal.presentation import clean_display_text, public_type_label


NOT_PROVIDED = "未提供"

CLOUD_TABLE_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "web3": (
        ("sector", "賽道"),
        ("status", "狀態"),
        ("thesis", "論點"),
        ("updated_at", "更新時間"),
    ),
    "food": (
        ("name", "店名"),
        ("area", "區域"),
        ("rating", "評分"),
        ("address", "地址"),
        ("hours", "營業時間"),
        ("price", "價位"),
        ("features", "特色"),
    ),
    "ai": (
        ("kind", "類型"),
        ("tool", "工具/Agent"),
        ("workflow", "工作流"),
        ("reliability", "可靠度"),
    ),
}

_COLUMN_LABELS: dict[str, str] = {
    key: label for columns in CLOUD_TABLE_COLUMNS.values() for key, label in columns
}

_COLUMN_EXTRACTORS: dict[str, Callable[[KnowledgeItem], str]] = {
    "sector": lambda item: item.concepts[0] if item.concepts else "",
    "status": lambda item: "",
    "thesis": lambda item: clean_display_text(item.summary),
    "updated_at": lambda item: item.updated_at,
    "name": lambda item: str((item.place or {}).get("name") or item.title),
    "area": lambda item: str((item.place or {}).get("area") or ""),
    "rating": lambda item: "",
    "address": lambda item: str((item.place or {}).get("address") or ""),
    "hours": lambda item: "",
    "price": lambda item: "",
    "features": lambda item: ", ".join(item.concepts),
    "kind": lambda item: public_type_label(item.item_type),
    "tool": lambda item: item.title,
    "workflow": lambda item: ", ".join(item.concepts),
    "reliability": lambda item: "",
}


def column_choices_for_cloud(cloud_key: str) -> tuple[tuple[str, str], ...]:
    return CLOUD_TABLE_COLUMNS[cloud_key]


def build_table(
    items: Sequence[KnowledgeItem],
    columns: Sequence[str],
    filters: Mapping[str, str],
) -> DerivedTable:
    filtered = _apply_filters(items, filters)
    columns = tuple(columns)
    rows = tuple(
        TableRow(
            source_id=item.source_id,
            title=item.title,
            url=f"/item/{item.source_id}",
            updated_at=item.updated_at,
            values=tuple(_format_cell(_extract(item, column)) for column in columns),
        )
        for item in filtered
    )
    view = DerivedView(
        kind="table",
        cloud_key=filtered[0].cloud_key if filtered else "",
        columns=columns,
        filters=tuple(sorted(filters.items())),
    )
    return DerivedTable(
        view=view,
        column_labels=tuple(_COLUMN_LABELS.get(column, column) for column in columns),
        rows=rows,
    )


def _extract(item: KnowledgeItem, column: str) -> str:
    extractor = _COLUMN_EXTRACTORS.get(column)
    return extractor(item) if extractor is not None else ""


def _format_cell(value: str) -> str:
    text = (value or "").strip()
    return text if text else NOT_PROVIDED


def _apply_filters(
    items: Sequence[KnowledgeItem], filters: Mapping[str, str]
) -> tuple[KnowledgeItem, ...]:
    cloud_key = filters.get("cloud")
    item_type = filters.get("type")
    concept = filters.get("concept")
    result = []
    for item in items:
        if cloud_key and item.cloud_key != cloud_key:
            continue
        if item_type and item.item_type != item_type:
            continue
        if concept and concept not in item.concepts:
            continue
        result.append(item)
    return tuple(result)


def source_refs_for_view(table: DerivedTable) -> tuple[str, ...]:
    return tuple(row.source_id for row in table.rows)


CHART_TYPES = ("bar", "donut", "timeline")


def build_chart(table: DerivedTable, chart_type: str) -> ChartSpec:
    if chart_type not in CHART_TYPES:
        raise ValueError(f"unsupported chart_type: {chart_type}")

    if chart_type == "timeline":
        axis_label = "更新月份"
        groups = _group_by_month(table)
    else:
        axis_label = table.column_labels[0] if table.column_labels else "分類"
        groups = _group_by_first_column(table)

    labels = tuple(groups.keys())
    values = tuple(float(len(ids)) for ids in groups.values())
    source_ids = tuple(source_id for ids in groups.values() for source_id in ids)
    return ChartSpec(
        chart_type=chart_type,
        title=f"{axis_label}分佈",
        axis_label=axis_label,
        labels=labels,
        values=values,
        summary=_chart_summary(axis_label, groups),
        source_ids=source_ids,
    )


def _group_by_first_column(table: DerivedTable) -> dict[str, tuple[str, ...]]:
    buckets: dict[str, list[str]] = {}
    for row in table.rows:
        value = row.values[0] if row.values else NOT_PROVIDED
        buckets.setdefault(value, []).append(row.source_id)
    ordered = sorted(buckets.items(), key=lambda pair: (-len(pair[1]), pair[0]))
    return {label: tuple(ids) for label, ids in ordered}


def _group_by_month(table: DerivedTable) -> dict[str, tuple[str, ...]]:
    buckets: dict[str, list[str]] = {}
    for row in table.rows:
        month = row.updated_at[:7] if len(row.updated_at) >= 7 else NOT_PROVIDED
        buckets.setdefault(month, []).append(row.source_id)
    ordered = sorted(buckets.items(), key=lambda pair: pair[0])
    return {label: tuple(ids) for label, ids in ordered}


def _chart_summary(axis_label: str, groups: dict[str, tuple[str, ...]]) -> str:
    if not groups:
        return f"目前沒有資料可以建立{axis_label}分佈圖。"
    parts = [f"{label} {len(ids)} 筆" for label, ids in groups.items()]
    return f"依{axis_label}分佈：" + "、".join(parts) + "。"


def serialize_view(view: DerivedView) -> str:
    return json.dumps(
        {
            "kind": view.kind,
            "cloud_key": view.cloud_key,
            "columns": list(view.columns),
            "filters": [list(pair) for pair in view.filters],
            "sort": view.sort,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def deserialize_view(payload: str) -> DerivedView:
    try:
        data = json.loads(payload)
    except (TypeError, ValueError) as error:
        raise ValueError("invalid view configuration") from error
    if not isinstance(data, dict):
        raise ValueError("invalid view configuration")
    try:
        return DerivedView(
            kind=str(data["kind"]),
            cloud_key=str(data["cloud_key"]),
            columns=tuple(str(value) for value in data["columns"]),
            filters=tuple((str(k), str(v)) for k, v in data.get("filters", [])),
            sort=str(data["sort"]) if data.get("sort") else None,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid view configuration") from error


_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _neutralize_formula(value: str) -> str:
    """Prevent CSV/Markdown-to-spreadsheet formula injection (CWE-1236):
    a cell starting with =, +, -, or @ gets interpreted as a formula by
    Excel/Sheets. Source content (titles, concepts, summaries) is free-form
    and not trusted to avoid these characters."""
    if value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def render_table_csv(table: DerivedTable) -> str:
    include_updated_at = "updated_at" not in table.view.columns
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    trailer = ("來源連結", "更新時間") if include_updated_at else ("來源連結",)
    writer.writerow(("標題", *table.column_labels, *trailer))
    for row in table.rows:
        trailer_values = (row.url, row.updated_at) if include_updated_at else (row.url,)
        writer.writerow(
            _neutralize_formula(cell)
            for cell in (row.title, *row.values, *trailer_values)
        )
    return buffer.getvalue()


def render_table_markdown(table: DerivedTable) -> str:
    include_updated_at = "updated_at" not in table.view.columns
    trailer = ("來源連結", "更新時間") if include_updated_at else ("來源連結",)
    header = ("標題", *table.column_labels, *trailer)
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in table.rows:
        trailer_values = (row.url, row.updated_at) if include_updated_at else (row.url,)
        cells = (row.title, *row.values, *trailer_values)
        lines.append(
            "| "
            + " | ".join(_neutralize_formula(cell.replace("|", "\\|")) for cell in cells)
            + " |"
        )
    return "\n".join(lines)
