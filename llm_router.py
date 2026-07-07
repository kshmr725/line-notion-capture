from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import requests

from config import settings


ALLOWED_CATEGORIES = {"Inbox", "Idea", "Task", "Reference", "Question", "Personal", "Other"}
JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class LLMResult:
    title: str
    summary: str
    category: str
    tags: list[str]
    provider: str
    degraded: bool = False


def fallback_result(raw_text: str) -> LLMResult:
    title = raw_text.strip().splitlines()[0][:80] if raw_text.strip() else "LINE 收件"
    return LLMResult(
        title=title or "LINE 收件",
        summary="AI 目前不可用，已保存原始內容。",
        category="Inbox",
        tags=[],
        provider="degraded",
        degraded=True,
    )


def parse_llm_json(text: str, provider: str) -> LLMResult:
    match = JSON_RE.search(text)
    if not match:
        raise ValueError("LLM did not return JSON")
    data: dict[str, Any] = json.loads(match.group(0))
    category = str(data.get("category") or "Inbox")
    if category not in ALLOWED_CATEGORIES:
        category = "Other"
    tags = data.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    return LLMResult(
        title=str(data.get("title") or "LINE 收件")[:100],
        summary=str(data.get("summary") or "")[:500],
        category=category,
        tags=[str(t).strip()[:24] for t in tags if str(t).strip()][:5],
        provider=provider,
    )


def prompt(raw_text: str, source_type: str) -> str:
    return (
        "你是 LINE 收件整理助手。請把使用者輸入整理成 Notion database 欄位。"
        "只回 JSON,不要 markdown。格式:"
        '{"title":"短標題","summary":"繁體中文摘要","category":"Inbox|Idea|Task|Reference|Question|Personal|Other","tags":["最多5個短標籤"]}'
        f"\n\nsource_type:{source_type}\nraw:\n{raw_text[:6000]}"
    )


def call_gemini(raw_text: str, source_type: str) -> LLMResult:
    if not settings.gemini_api_key:
        raise RuntimeError("missing GEMINI_API_KEY")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent"
    )
    resp = requests.post(
        url,
        params={"key": settings.gemini_api_key},
        json={"contents": [{"parts": [{"text": prompt(raw_text, source_type)}]}]},
        timeout=35,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return parse_llm_json(text, "gemini")


def call_deepseek(raw_text: str, source_type: str) -> LLMResult:
    if not settings.deepseek_api_key:
        raise RuntimeError("missing DEEPSEEK_API_KEY")
    resp = requests.post(
        "https://api.deepseek.com/chat/completions",
        json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt(raw_text, source_type)}],
            "temperature": 0.2,
        },
        headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
        timeout=35,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    return parse_llm_json(text, "deepseek")


def organize(raw_text: str, source_type: str = "text") -> LLMResult:
    if settings.dry_run:
        return LLMResult(
            title="乾跑測試收件",
            summary=f"這是一則 {source_type} 測試訊息，正式環境會由 Gemini 優先整理、DeepSeek 備援。",
            category="Inbox",
            tags=["dry-run"],
            provider="degraded",
            degraded=True,
        )
    try:
        return call_gemini(raw_text, source_type)
    except Exception:
        pass
    try:
        return call_deepseek(raw_text, source_type)
    except Exception:
        return fallback_result(raw_text)
