from __future__ import annotations

import math
import re
from html import unescape
from typing import Any

import yaml
from markupsafe import Markup, escape

_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}\s*")
_CATEGORY_PREFIX = re.compile(r"^\[[^\]]+\]\s*")
_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_ALLOWED = {"title", "location", "address", "area", "category", "status"}
_ALIASES = {"咖啡店": "咖啡廳", "黑膠咖啡": "咖啡廳", "甜點店": "甜點"}
_CLOUD_ICONS = {"web3": "orbit", "food": "map-pin", "ai": "workflow"}
_PUBLIC_CLOUD_LABELS = {"web3": "Web3", "food": "美食地圖", "ai": "AI 自動化"}
_TYPE_ICONS = {
    "research": "file-text",
    "report": "file-text",
    "project": "layers",
    "concept": "nodes",
    "tool": "wrench",
    "agent": "robot",
    "mcp": "plug",
    "workflow": "branch",
    "guide": "book",
    "news": "newspaper",
}
_PUBLIC_TYPE_LABELS = {
    "research": "研究筆記",
    "report": "研究報告",
    "project": "專案",
    "concept": "主題",
    "place": "地點",
    "tool": "工具",
    "agent": "Agent",
    "mcp": "MCP",
    "workflow": "工作流",
    "guide": "教學",
    "news": "新聞",
}


def icon_name_for_cloud(cloud_key: str) -> str:
    return _CLOUD_ICONS.get(cloud_key, "grid")


def public_cloud_label(cloud_key: str) -> str:
    return _PUBLIC_CLOUD_LABELS.get(str(cloud_key).lower(), str(cloud_key))


def icon_name_for_item(item: Any) -> str:
    if getattr(item, "place", None) is not None:
        category = str(item.place.get("category", ""))
        if "咖啡" in category:
            return "coffee"
        if "酒" in category:
            return "glass"
        if "甜點" in category:
            return "cake"
        return "utensils"
    return _TYPE_ICONS.get(str(getattr(item, "item_type", "")).lower(), "file-text")


def public_type_label(item_type: str) -> str:
    return _PUBLIC_TYPE_LABELS.get(str(item_type).lower(), "筆記")


def clean_display_text(value: str) -> str:
    """Remove source markup from short reader-facing labels and summaries."""
    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[*_~`]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def render_markdown_body(body: str) -> Markup:
    """Render the small Markdown subset used by source notes safely.

    The portal is a reader, not an editor.  Rendering headings, emphasis,
    links, lists, and Obsidian callouts here prevents source syntax from
    leaking into the UI while keeping arbitrary HTML escaped.
    """
    output: list[str] = []
    list_open = False

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            output.append("</ul>")
            list_open = False

    for raw_line in str(body or "").replace("\r\n", "\n").splitlines():
        line = raw_line.strip()
        if not line:
            close_list()
            continue
        line = re.sub(r"^K#\s+", "# ", line)
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            close_list()
            level = max(2, min(6, len(heading.group(1)) + 1))
            output.append(f"<h{level}>{_render_inline(heading.group(2))}</h{level}>")
            continue
        callout = re.match(r"^>\s*\[!(tip|important|warning|note)\]\s*(.*)$", line)
        if callout:
            close_list()
            kind, content = callout.groups()
            output.append(
                f'<aside class="source-callout source-callout-{kind}">{_render_inline(content)}</aside>'
            )
            continue
        bullet = re.match(r"^(?:[-*]|\d+\.)\s+(.+)$", line)
        if bullet:
            if not list_open:
                output.append("<ul>")
                list_open = True
            output.append(f"<li>{_render_inline(bullet.group(1))}</li>")
            continue
        close_list()
        output.append(f"<p>{_render_inline(line)}</p>")
    close_list()
    return Markup("\n".join(output))


def _render_inline(value: str) -> str:
    link_pattern = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
    chunks: list[str] = []
    cursor = 0
    for match in link_pattern.finditer(value):
        chunks.append(_render_emphasis(value[cursor : match.start()]))
        chunks.append(
            f'<a href="{escape(match.group(2))}" rel="noreferrer">'
            f"{_render_emphasis(match.group(1))}</a>"
        )
        cursor = match.end()
    chunks.append(_render_emphasis(value[cursor:]))
    return "".join(chunks)


def _render_emphasis(value: str) -> str:
    escaped = str(escape(value)).replace("&lt;br&gt;", "<br>")
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)


_PLACE_FACT_PATTERNS = (
    ("評價", r"(?:⭐\s*)?(?:\*\*)?評價(?:\*\*)?\s*[:：]\s*(.*?)(?=\s*(?:📍|地址|🕒|時間|💰|價位[／/]特色|$))"),
    ("地址", r"(?:📍\s*)?(?:\*\*)?地址(?:\*\*)?\s*[:：]\s*(.*?)(?=\s*(?:⭐|評價|🕒|時間|💰|價位[／/]特色|$))"),
    ("營業時間", r"(?:🕒\s*)?(?:\*\*)?(?:時間|營業時間)(?:\*\*)?\s*[:：]\s*(.*?)(?=\s*(?:⭐|評價|📍|地址|💰|價位[／/]特色|$))"),
    ("價位／特色", r"(?:💰\s*)?(?:\*\*)?價位[／/]特色(?:\*\*)?\s*[:：]\s*(.*?)(?=\s*(?:⭐|評價|📍|地址|🕒|時間|#|📌|💡|⚡|🗺️|$))"),
)
_PLACE_KEY_LABELS = (
    ("rating", "評價"),
    ("address", "地址"),
    ("area", "區域"),
    ("opening_hours", "營業時間"),
    ("hours", "營業時間"),
    ("time", "營業時間"),
    ("price", "價位／特色"),
    ("price_range", "價位／特色"),
    ("features", "特色"),
    ("highlights", "特色"),
)


def place_facts(
    place: dict[str, object] | None,
    summary: str = "",
    body: str = "",
) -> list[dict[str, str]]:
    """Return only reader-useful facts for a food/place card.

    Coordinates remain available to the map layer, but are intentionally not
    part of this public presentation contract.
    """
    if not place:
        return []
    facts: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(label: str, value: object) -> None:
        if value is None:
            return
        cleaned = clean_display_text(str(value))
        if not cleaned or label in seen:
            return
        seen.add(label)
        facts.append({"label": label, "value": cleaned})

    add("類型", place.get("category"))
    for key, label in _PLACE_KEY_LABELS:
        add(label, place.get(key))

    for source in (summary, body):
        source_text = clean_display_text(source)
        if not source_text:
            continue
        for label, pattern in _PLACE_FACT_PATTERNS:
            if label in seen:
                continue
            match = re.search(pattern, source_text, flags=re.IGNORECASE)
            if match:
                add(label, match.group(1).strip(" \t\r\n。"))
    return facts

def clean_display_title(value: str) -> str:
    value = _DATE_PREFIX.sub("", value.strip())
    value = _CATEGORY_PREFIX.sub("", value)
    value = re.sub(r"^[^\w\u4e00-\u9fff]+\s*", "", value)
    return re.sub(r"\s+", " ", value.strip())

def parse_obsidian_metadata(body: str, filename_title: str) -> dict[str, object]:
    frontmatter, visible = _frontmatter(body)
    h1 = _H1.search(visible)
    title = frontmatter.get("title") or (h1.group(1) if h1 else filename_title)
    return {"title": clean_display_title(str(title)), "frontmatter": frontmatter}

def food_place_metadata(body: str, filename_title: str) -> dict[str, object]:
    parsed = parse_obsidian_metadata(body, filename_title)
    frontmatter = parsed["frontmatter"]
    match = re.search(r"\[([^\]]+)\]", filename_title)
    category = str(frontmatter.get("category") or (match.group(1) if match else "")).strip()
    place: dict[str, object] = {"name": parsed["title"] or clean_display_title(filename_title)}
    if category:
        place["category"] = _ALIASES.get(category, category)
    for field in ("address", "area", "status"):
        if isinstance(frontmatter.get(field), str) and frontmatter[field].strip():
            place[field] = frontmatter[field].strip()
    coordinates = _coordinates(frontmatter.get("location"))
    if coordinates is not None:
        place["latitude"], place["longitude"] = coordinates
    return {"item_type": "place", "place": place, "display_title": parsed["title"]}

def _frontmatter(body: str) -> tuple[dict[str, Any], str]:
    if not body.startswith("---\n"):
        return {}, body
    closing = body.find("\n---\n", 4)
    if closing < 0:
        return {}, body
    loaded = yaml.safe_load(body[4:closing])
    values = loaded if isinstance(loaded, dict) else {}
    return {key: values[key] for key in _ALLOWED & values.keys()}, body[closing + 5:].lstrip()

def _coordinates(value: object) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        latitude, longitude = (float(part) for part in value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        return None
    return (latitude, longitude) if -90 <= latitude <= 90 and -180 <= longitude <= 180 else None
