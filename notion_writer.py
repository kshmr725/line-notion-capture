from __future__ import annotations

from datetime import datetime, timezone

import requests

from config import settings
from llm_router import LLMResult
from taxonomy import time_bucket


NOTION_VERSION = "2022-06-28"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.notion_token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _paragraph(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text[:1900]}}]},
    }


def _heading(text: str) -> dict:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": text[:100]}}]},
    }


def _bullets(text: str) -> list[dict]:
    lines = [line.strip().removeprefix("-").strip() for line in (text or "").splitlines() if line.strip()]
    return [
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line[:1900]}}]},
        }
        for line in lines[:8]
    ]


def _callout(text: str, emoji: str) -> dict:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": emoji},
            "rich_text": [{"type": "text", "text": {"content": text[:1900]}}],
        },
    }


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _optional_rich_text(value: str) -> dict:
    return {"rich_text": [{"text": {"content": value[:1900]}}]} if value else {"rich_text": []}


def _optional_select(value: str) -> dict:
    return {"select": {"name": value[:100]}} if value else {"select": None}


def _get_database_properties() -> dict:
    response = requests.get(
        f"https://api.notion.com/v1/databases/{settings.notion_database_id}",
        headers=_headers(),
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("properties", {})


def _patch_database_properties(properties: dict) -> None:
    desired = {
        "Folder": {"rich_text": {}},
        "Category Reason": {"rich_text": {}},
        "Capture Date": {"date": {}},
        "Time Bucket": {"select": {}},
        "Action": {"rich_text": {}},
        "Key Point": {"rich_text": {}},
    }
    missing = {name: config for name, config in desired.items() if name not in properties}
    if not missing:
        return
    response = requests.patch(
        f"https://api.notion.com/v1/databases/{settings.notion_database_id}",
        headers=_headers(),
        json={"properties": missing},
        timeout=20,
    )
    response.raise_for_status()
    properties.update(missing)


def create_capture_page(
    result: LLMResult,
    raw_input: str,
    source_user: str,
    source_type: str,
    line_message_id: str,
    attachment_url: str = "",
) -> str:
    created_at = datetime.now(timezone.utc)
    if settings.dry_run:
        print(
            "[NOTION DRY RUN page]",
            {
                "title": result.title,
                "category": result.category,
                "source_user": source_user,
                "source_type": source_type,
                "raw_input": raw_input,
            },
        )
        return "https://notion.example/dry-run"
    if not settings.notion_token or not settings.notion_database_id:
        raise RuntimeError("missing Notion settings")
    database_properties = _get_database_properties()
    try:
        _patch_database_properties(database_properties)
    except requests.RequestException:
        pass
    properties = {
        "Name": {"title": [{"text": {"content": result.title or "LINE 收件"}}]},
        "Status": {"status": {"name": "Not started"}},
        "Category": {"select": {"name": result.category}},
        "Source User": {"rich_text": [{"text": {"content": source_user[:200]}}]},
        "Source Type": {"select": {"name": source_type}},
        "Raw Input": {"rich_text": [{"text": {"content": raw_input[:1900]}}]},
        "Summary": {"rich_text": [{"text": {"content": result.summary[:1900]}}]},
        "Tags": {"multi_select": [{"name": tag} for tag in result.tags]},
        "AI Provider": {"select": {"name": result.provider}},
        "LINE Message ID": {"rich_text": [{"text": {"content": line_message_id[:200]}}]},
        "Created At": {"date": {"start": created_at.isoformat()}},
    }
    optional_properties = {
        "Folder": _optional_rich_text(result.folder),
        "Category Reason": _optional_rich_text(result.category_reason),
        "Capture Date": {"date": {"start": created_at.date().isoformat()}},
        "Time Bucket": _optional_select(time_bucket(created_at)),
        "Action": _optional_rich_text(result.action),
        "Key Point": _optional_rich_text(result.key_point),
    }
    for name, value in optional_properties.items():
        if name in database_properties:
            properties[name] = value
    if attachment_url:
        properties["Attachment URL"] = {"url": attachment_url}
    children = [
        _callout(f"分類：{result.category} / {result.folder}\n依據：{result.category_reason}", "📂"),
        _callout(result.what or result.summary or "已收進 Notion。", "📌"),
        _callout(result.key_point or result.summary or "尚無重點。", "💡"),
        _callout(result.action or "先保留，之後可補上自己的判斷與下一步。", "⚡"),
        _divider(),
        _heading("重點摘要"),
    ]
    bullets = _bullets(result.detail)
    children.extend(bullets or [_paragraph(result.summary or "AI 未產生摘要。")])
    children.extend(
        [
            _heading("原始訊息"),
            _paragraph(raw_input),
            _heading("來源資訊"),
            _paragraph(f"source_user: {source_user}\nsource_type: {source_type}\nai_provider: {result.provider}"),
        ]
    )
    payload = {
        "parent": {"database_id": settings.notion_database_id},
        "properties": properties,
        "children": children,
    }
    resp = requests.post("https://api.notion.com/v1/pages", json=payload, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json().get("url", "")
