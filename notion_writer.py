from __future__ import annotations

from datetime import datetime, timezone

import requests

from config import settings
from llm_router import LLMResult


NOTION_VERSION = "2022-06-28"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.notion_token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def create_capture_page(
    result: LLMResult,
    raw_input: str,
    source_user: str,
    source_type: str,
    line_message_id: str,
    attachment_url: str = "",
) -> str:
    if not settings.notion_token or not settings.notion_database_id:
        raise RuntimeError("missing Notion settings")
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
        "Created At": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
    }
    if attachment_url:
        properties["Attachment URL"] = {"url": attachment_url}
    payload = {
        "parent": {"database_id": settings.notion_database_id},
        "properties": properties,
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": raw_input[:1900]}}]},
            }
        ],
    }
    resp = requests.post("https://api.notion.com/v1/pages", json=payload, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json().get("url", "")
