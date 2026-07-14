from __future__ import annotations

import math
import re
from html import unescape
from typing import Any

import yaml

_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}\s*")
_CATEGORY_PREFIX = re.compile(r"^\[[^\]]+\]\s*")
_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_ALLOWED = {"title", "location", "address", "area", "category", "status"}
_ALIASES = {"咖啡店": "咖啡廳", "黑膠咖啡": "咖啡廳", "甜點店": "甜點"}
_CLOUD_ICONS = {"web3": "orbit", "food": "map-pin", "ai": "workflow"}
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


def icon_name_for_cloud(cloud_key: str) -> str:
    return _CLOUD_ICONS.get(cloud_key, "grid")


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


def clean_display_text(value: str) -> str:
    """Remove source markup from short reader-facing labels and summaries."""
    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[*_~`]+", "", text)
    return re.sub(r"\s+", " ", text).strip()

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
