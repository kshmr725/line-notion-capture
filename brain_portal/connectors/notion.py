from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import requests

from brain_portal.models import SourceDocument


NOTION_API_BASE = "https://api.notion.com/v1"
MAX_PAGINATION_ROUNDS = 100

CLOUD_KEY_MAP = {
    "AI Automation": "ai",
    "Web3 Research": "web3",
    "Food and Places": "food",
}


class NotionConnector:
    source_type = "notion"

    def __init__(self, token: str, database_id: str, api_version: str, timeout: float = 20):
        self.token = _required(token, "Notion token")
        self.database_id = _required(database_id, "Notion database id")
        self.api_version = _required(api_version, "Notion API version")
        self.timeout = timeout

    def iter_documents(self, tenant_id: str) -> Iterable[SourceDocument]:
        for page in self._iter_database_pages():
            yield self._document_from_page(tenant_id, page)

    def fetch_document(self, tenant_id: str, page_id: str) -> SourceDocument:
        page = self._retrieve_page(page_id)
        return self._document_from_page(tenant_id, page)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.api_version,
            "Content-Type": "application/json",
        }

    def _iter_database_pages(self):
        cursor = None
        for _ in range(MAX_PAGINATION_ROUNDS):
            payload = {"page_size": 100}
            if cursor:
                payload["start_cursor"] = cursor
            response = requests.post(
                f"{NOTION_API_BASE}/databases/{self.database_id}/query",
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
            self._raise_for_permission(response)
            response.raise_for_status()
            body = response.json()
            for page in body.get("results", []):
                yield page
            if not body.get("has_more"):
                return
            cursor = body.get("next_cursor")
        raise RuntimeError("Notion database pagination exceeded the safety bound")

    def _retrieve_page(self, page_id: str) -> dict:
        response = requests.get(
            f"{NOTION_API_BASE}/pages/{page_id}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        self._raise_for_permission(response)
        response.raise_for_status()
        return response.json()

    def _page_body(self, page_id: str) -> str:
        texts = []
        cursor = None
        for _ in range(MAX_PAGINATION_ROUNDS):
            params = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            response = requests.get(
                f"{NOTION_API_BASE}/blocks/{page_id}/children",
                headers=self._headers(),
                params=params,
                timeout=self.timeout,
            )
            self._raise_for_permission(response)
            response.raise_for_status()
            body = response.json()
            for block in body.get("results", []):
                text = _block_plain_text(block)
                if text:
                    texts.append(text)
            if not body.get("has_more"):
                break
            cursor = body.get("next_cursor")
        else:
            raise RuntimeError("Notion block pagination exceeded the safety bound")
        return "\n\n".join(texts)

    @staticmethod
    def _raise_for_permission(response) -> None:
        if response.status_code in (401, 403):
            raise PermissionError("Notion access was denied for this page or database")

    def _document_from_page(self, tenant_id: str, page: dict) -> SourceDocument:
        page_id = str(page.get("id", "")).strip()
        if not page_id:
            raise ValueError("Notion page is missing an id")
        properties = page.get("properties")
        properties = properties if isinstance(properties, dict) else {}
        title = _plain_title(_property_by_type(properties, "title")) or "Untitled"
        summary = _plain_rich_text(properties.get("Summary"))
        cloud_key = CLOUD_KEY_MAP.get(_select_name(properties.get("Cloud")), "")
        concepts = _multi_select_names(properties.get("Concepts"))
        canonical_ref = str(page.get("url", "")).strip()
        revision = str(page.get("last_edited_time", "")).strip()
        updated_at = revision or datetime.now(timezone.utc).isoformat()
        return SourceDocument(
            tenant_id=tenant_id,
            source_id=page_id,
            source_type=self.source_type,
            canonical_ref=canonical_ref,
            title=title,
            body=self._page_body(page_id),
            cloud_key=cloud_key,
            source_revision=revision,
            updated_at=updated_at,
            metadata={"summary": summary, "concepts": concepts},
        )


def _property_by_type(properties: dict, type_name: str) -> dict | None:
    for prop in properties.values():
        if isinstance(prop, dict) and prop.get("type") == type_name:
            return prop
    return None


def _plain_title(prop: dict | None) -> str:
    if not isinstance(prop, dict):
        return ""
    values = prop.get("title")
    if not isinstance(values, list):
        return ""
    return "".join(
        str(entry.get("plain_text", "")) for entry in values if isinstance(entry, dict)
    ).strip()


def _plain_rich_text(prop: dict | None) -> str:
    if not isinstance(prop, dict):
        return ""
    values = prop.get("rich_text")
    if not isinstance(values, list):
        return ""
    return "".join(
        str(entry.get("plain_text", "")) for entry in values if isinstance(entry, dict)
    ).strip()


def _select_name(prop: dict | None) -> str:
    if not isinstance(prop, dict):
        return ""
    select = prop.get("select")
    if not isinstance(select, dict):
        return ""
    return str(select.get("name", "")).strip()


def _multi_select_names(prop: dict | None) -> tuple[str, ...]:
    if not isinstance(prop, dict):
        return ()
    values = prop.get("multi_select")
    if not isinstance(values, list):
        return ()
    return tuple(
        str(entry.get("name", "")).strip()
        for entry in values
        if isinstance(entry, dict) and str(entry.get("name", "")).strip()
    )


def _block_plain_text(block: dict) -> str:
    if not isinstance(block, dict):
        return ""
    block_type = block.get("type")
    payload = block.get(block_type) if isinstance(block_type, str) else None
    if not isinstance(payload, dict):
        return ""
    rich_text = payload.get("rich_text")
    if not isinstance(rich_text, list):
        return ""
    return "".join(
        str(entry.get("plain_text", "")) for entry in rich_text if isinstance(entry, dict)
    ).strip()


def _required(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()
