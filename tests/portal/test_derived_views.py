from __future__ import annotations

import json

import pytest

from brain_portal.derived_views import (
    CLOUD_TABLE_COLUMNS,
    build_chart,
    build_slides,
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


def test_build_chart_web3_sector_groups_by_the_first_column():
    items = [
        _item("a", "A", cloud_key="web3", concepts=("restaking",)),
        _item("b", "B", cloud_key="web3", concepts=("restaking",)),
        _item("c", "C", cloud_key="web3", concepts=("mev",)),
    ]
    table = build_table(items, ("sector",), {})

    chart = build_chart(table, "bar")

    assert chart.chart_type == "bar"
    assert chart.axis_label == "賽道"
    assert dict(zip(chart.labels, chart.values)) == {"restaking": 2.0, "mev": 1.0}
    assert set(chart.source_ids) == {"a", "b", "c"}


def test_build_chart_food_groups_by_selected_column():
    items = [
        _item("a", "A", cloud_key="food", place={"name": "A", "area": "Da'an"}),
        _item("b", "B", cloud_key="food", place={"name": "B", "area": "Da'an"}),
        _item("c", "C", cloud_key="food", place={"name": "C", "area": "Xinyi"}),
    ]
    table = build_table(items, ("area",), {})

    chart = build_chart(table, "donut")

    assert dict(zip(chart.labels, chart.values)) == {"Da'an": 2.0, "Xinyi": 1.0}


def test_build_chart_ai_reliability_honestly_shows_the_未提供_bucket():
    items = [_item("a", "A", cloud_key="ai", item_type="agent")]
    table = build_table(items, ("reliability",), {})

    chart = build_chart(table, "bar")

    assert chart.labels == ("未提供",)
    assert chart.values == (1.0,)


def test_build_chart_timeline_groups_by_month():
    items = [
        _item("a", "A", updated_at="2026-07-01T00:00:00+00:00"),
        _item("b", "B", updated_at="2026-07-15T00:00:00+00:00"),
        _item("c", "C", updated_at="2026-06-01T00:00:00+00:00"),
    ]
    table = build_table(items, ("sector",), {})

    chart = build_chart(table, "timeline")

    assert chart.labels == ("2026-06", "2026-07")
    assert chart.values == (1.0, 2.0)


def test_build_chart_is_deterministic():
    items = [
        _item("a", "A", concepts=("restaking",)),
        _item("b", "B", concepts=("mev",)),
    ]
    table = build_table(items, ("sector",), {})

    first = build_chart(table, "bar")
    second = build_chart(table, "bar")

    assert first == second


def test_build_chart_summary_is_non_empty_accessible_text():
    items = [_item("a", "A", concepts=("restaking",))]
    table = build_table(items, ("sector",), {})

    chart = build_chart(table, "bar")

    assert chart.summary
    assert "restaking" in chart.summary


def test_build_chart_rejects_an_unsupported_chart_type():
    items = [_item("a", "A", concepts=("restaking",))]
    table = build_table(items, ("sector",), {})

    with pytest.raises(ValueError):
        build_chart(table, "pie")


def test_build_chart_handles_an_empty_table_safely():
    table = build_table([], ("sector",), {})

    chart = build_chart(table, "bar")

    assert chart.labels == ()
    assert chart.values == ()
    assert chart.summary


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


def test_build_slides_creates_source_linked_claim_clusters():
    items = [
        _item(
            "a",
            "Restaking Thesis",
            concepts=("restaking", "validators"),
            summary="Restaking lets validators secure multiple networks.",
            updated_at="2026-07-10T00:00:00+00:00",
        ),
        _item(
            "b",
            "MEV Research",
            concepts=("mev",),
            summary="MEV changes the order in which transactions execute.",
            updated_at="2026-07-11T00:00:00+00:00",
        ),
    ]
    table = build_table(items, ("sector", "thesis"), {})

    slides = build_slides(table, "Web3 研究簡報")

    assert slides[0].title == "Web3 研究簡報"
    assert "2 筆" in slides[0].body
    assert slides[0].source_ids == ("a", "b")
    assert [slide.title for slide in slides[1:]] == [
        "Restaking Thesis",
        "MEV Research",
    ]
    assert slides[1].source_ids == ("a",)
    assert slides[1].updated_at == "2026-07-10T00:00:00+00:00"
    assert "賽道：restaking" in slides[1].body


def test_build_slides_handles_an_empty_table_without_fake_claims():
    table = build_table([], ("sector",), {})

    slides = build_slides(table, "空白研究簡報")

    assert len(slides) == 1
    assert slides[0].source_ids == ()
    assert "沒有資料" in slides[0].body
