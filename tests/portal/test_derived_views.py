from __future__ import annotations

import json

import pytest

from brain_portal.derived_views import (
    CLOUD_TABLE_COLUMNS,
    build_table,
    column_choices_for_cloud,
    deserialize_view,
    render_table_csv,
    render_table_markdown,
    serialize_view,
    source_refs_for_view,
)
from brain_portal.models import DerivedView, KnowledgeItem


def _item(
    source_id: str,
    title: str,
    cloud_key: str = "web3",
    item_type: str = "research",
    concepts: tuple[str, ...] = (),
    place: dict | None = None,
    summary: str = "",
    updated_at: str = "2026-07-14T00:00:00+00:00",
    canonical_ref: str | None = None,
) -> KnowledgeItem:
    return KnowledgeItem(
        tenant_id="tenant-1",
        source_id=source_id,
        source_type="obsidian",
        canonical_ref=canonical_ref or f"obsidian://{source_id}",
        title=title,
        summary=summary,
        body="body",
        cloud_key=cloud_key,
        item_type=item_type,
        concepts=concepts,
        place=place,
        source_revision="rev-1",
        updated_at=updated_at,
    )


def test_build_table_web3_columns_extracts_deterministic_values():
    items = [
        _item(
            "a",
            "Restaking Thesis 2026",
            concepts=("restaking", "validators"),
            summary="Restaking lets validators secure multiple networks.",
            updated_at="2026-07-10T00:00:00+00:00",
        )
    ]

    table = build_table(items, ("sector", "status", "thesis", "updated_at"), {})

    [row] = table.rows
    assert row.values[0] == "restaking"
    assert row.values[1] == "未提供"
    assert row.values[2] == "Restaking lets validators secure multiple networks."
    assert row.values[3] == "2026-07-10T00:00:00+00:00"
    assert row.source_id == "a"
    assert row.title == "Restaking Thesis 2026"


def test_build_table_food_columns_extracts_deterministic_values():
    items = [
        _item(
            "b",
            "Quiet Noodle Shop",
            cloud_key="food",
            place={
                "name": "Quiet Noodle Shop",
                "address": "1 Main St",
                "area": "Da'an",
                "latitude": 25.03,
                "longitude": 121.53,
            },
            concepts=("noodles", "quiet"),
        )
    ]

    table = build_table(
        items, ("name", "rating", "address", "hours", "price", "features"), {}
    )

    [row] = table.rows
    assert row.values[0] == "Quiet Noodle Shop"
    assert row.values[1] == "未提供"
    assert row.values[2] == "1 Main St"
    assert row.values[3] == "未提供"
    assert row.values[4] == "未提供"
    assert row.values[5] == "noodles, quiet"


def test_build_table_ai_columns_extracts_deterministic_values():
    items = [
        _item(
            "c",
            "Build Reliable Agents",
            cloud_key="ai",
            item_type="agent",
            concepts=("boundaries", "fallbacks"),
        )
    ]

    table = build_table(items, ("kind", "tool", "workflow", "reliability"), {})

    [row] = table.rows
    assert row.values[0] == "Agent"
    assert row.values[1] == "Build Reliable Agents"
    assert row.values[2] == "boundaries, fallbacks"
    assert row.values[3] == "未提供"


def test_build_table_never_leaks_raw_coordinates_into_any_cell():
    items = [
        _item(
            "d",
            "Cafe",
            cloud_key="food",
            place={"name": "Cafe", "latitude": 25.03, "longitude": 121.53},
        )
    ]

    table = build_table(items, ("name", "address"), {})

    [row] = table.rows
    joined = " ".join(row.values)
    assert "25.03" not in joined
    assert "121.53" not in joined
    assert "None" not in joined


def test_build_table_is_deterministic_for_the_same_input():
    items = [_item("a", "A", concepts=("x",)), _item("b", "B", concepts=("y",))]

    first = build_table(items, ("sector", "thesis"), {})
    second = build_table(items, ("sector", "thesis"), {})

    assert first == second


def test_build_table_filters_by_item_type():
    items = [
        _item("a", "Tool note", cloud_key="ai", item_type="tool"),
        _item("b", "Agent note", cloud_key="ai", item_type="agent"),
    ]

    table = build_table(items, ("kind",), {"type": "tool"})

    assert [row.source_id for row in table.rows] == ["a"]


def test_build_table_filters_by_concept():
    items = [
        _item("a", "Note A", concepts=("restaking",)),
        _item("b", "Note B", concepts=("mev",)),
    ]

    table = build_table(items, ("sector",), {"concept": "mev"})

    assert [row.source_id for row in table.rows] == ["b"]


def test_source_refs_for_view_returns_ids_in_row_order():
    items = [_item("a", "A"), _item("b", "B"), _item("c", "C")]

    table = build_table(items, ("sector",), {})

    assert source_refs_for_view(table) == ("a", "b", "c")


def test_column_choices_for_cloud_returns_labeled_pairs():
    choices = column_choices_for_cloud("web3")

    assert ("sector", "賽道") in choices
    assert choices == CLOUD_TABLE_COLUMNS["web3"]


def test_column_choices_for_cloud_rejects_an_unknown_cloud():
    with pytest.raises(KeyError):
        column_choices_for_cloud("not-a-real-cloud")


def test_serialize_and_deserialize_view_round_trips():
    view = DerivedView(
        kind="table",
        cloud_key="web3",
        columns=("sector", "thesis"),
        filters=(("type", "research"),),
        sort="updated_at",
    )

    payload = serialize_view(view)
    restored = deserialize_view(payload)

    assert restored == view
    json.loads(payload)


def test_deserialize_view_rejects_malformed_json():
    with pytest.raises(ValueError):
        deserialize_view("not-json")


def test_render_table_csv_includes_header_and_source_links():
    items = [_item("a", "Restaking Thesis", concepts=("restaking",))]
    table = build_table(items, ("sector",), {})

    csv_text = render_table_csv(table)

    lines = csv_text.strip().splitlines()
    assert lines[0] == "標題,賽道,來源連結,更新時間"
    assert "Restaking Thesis" in lines[1]
    assert "/item/a" in lines[1]


@pytest.mark.parametrize("formula", ["=1+1", "+1+1", "-1+1", "@SUM(1)"])
def test_render_table_csv_neutralizes_formula_injection(formula):
    items = [_item("a", formula, concepts=(formula,))]
    table = build_table(items, ("sector",), {})

    csv_text = render_table_csv(table)

    lines = csv_text.strip().splitlines()
    assert not lines[1].startswith(formula)
    assert formula in lines[1]


@pytest.mark.parametrize("formula", ["=1+1", "+1+1", "-1+1", "@SUM(1)"])
def test_render_table_markdown_neutralizes_formula_injection(formula):
    items = [_item("a", formula, concepts=(formula,))]
    table = build_table(items, ("sector",), {})

    markdown = render_table_markdown(table)

    assert f"| {formula} |" not in markdown
    assert formula in markdown


def test_render_table_csv_never_duplicates_the_updated_at_column():
    items = [_item("a", "Restaking Thesis", concepts=("restaking",))]
    table = build_table(items, ("sector", "updated_at"), {})

    csv_text = render_table_csv(table)

    header = csv_text.strip().splitlines()[0]
    assert header.count("更新時間") == 1


def test_render_table_markdown_includes_header_and_rows():
    items = [_item("a", "Restaking Thesis", concepts=("restaking",))]
    table = build_table(items, ("sector",), {})

    markdown = render_table_markdown(table)

    assert "| 標題 | 賽道 | 來源連結 | 更新時間 |" in markdown
    assert "Restaking Thesis" in markdown
    assert "/item/a" in markdown
