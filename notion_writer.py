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


def create_capture_page(
    result: LLMResult,
    raw_input: str,
    source_user: str,
    source_type: str,
    line_message_id: str,
    attachment_url: str = "",
) -> str:
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
            _heading("摘要"),
            _paragraph(result.summary or "AI 未產生摘要。"),
            _heading("原始訊息"),
            _paragraph(raw_input),
            _heading("來源資訊"),
            _paragraph(f"source_user: {source_user}\nsource_type: {source_type}\nai_provider: {result.provider}"),
        ],
    }
    resp = requests.post("https://api.notion.com/v1/pages", json=payload, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json().get("url", "")
