from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import requests

from config import settings
from taxonomy import Classification, classify


JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class LLMResult:
    title: str
    summary: str
    category: str
    folder: str
    category_key: str
    category_reason: str
    what: str
    key_point: str
    action: str
    detail: str
    tags: list[str]
    provider: str
    degraded: bool = False


def fallback_result(raw_text: str, classification: Classification | None = None) -> LLMResult:
    classification = classification or classify(raw_text)
    title = raw_text.strip().splitlines()[0][:80] if raw_text.strip() else "LINE 收件"
    return LLMResult(
        title=title or "LINE 收件",
        summary="AI 目前不可用，已保存原始內容。",
        category=classification.label,
        folder=classification.folder,
        category_key=classification.key,
        category_reason=classification.reason_text(),
        what=title or "LINE 收件",
        key_point="AI 目前不可用，已先保留原始內容。",
        action="稍後可以回來補整理，或重新傳送一次。",
        detail=raw_text[:1200],
        tags=[],
        provider="degraded",
        degraded=True,
    )


def _list_of_strings(value: Any, limit: int = 5, item_limit: int = 80) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:item_limit] for item in value if str(item).strip()][:limit]


def parse_llm_json(text: str, provider: str, classification: Classification | None = None) -> LLMResult:
    match = JSON_RE.search(text)
    if not match:
        raise ValueError("LLM did not return JSON")
    classification = classification or classify(text)
    data: dict[str, Any] = json.loads(match.group(0))
    title = str(data.get("title") or "LINE 收件")[:100]
    what = str(data.get("what") or data.get("summary") or title)[:500]
    key_point = str(data.get("key_point") or data.get("summary") or "")[:700]
    action = str(data.get("action") or "先保留，之後可補上自己的判斷與下一步。")[:500]
    detail_points = _list_of_strings(data.get("detail_points"), limit=6, item_limit=220)
    detail = str(data.get("detail") or "\n".join(f"- {point}" for point in detail_points))[:1800]
    summary = str(data.get("summary") or key_point or what)[:900]
    return LLMResult(
        title=title,
        summary=summary,
        category=classification.label,
        folder=classification.folder,
        category_key=classification.key,
        category_reason=classification.reason_text(),
        what=what,
        key_point=key_point,
        action=action,
        detail=detail,
        tags=_list_of_strings(data.get("tags"), limit=5, item_limit=24),
        provider=provider,
    )


def prompt(raw_text: str, source_type: str, classification: Classification) -> str:
    return (
        "你是 LINE 收件整理助手。請把使用者輸入整理成朋友也能快速閱讀的繁體中文筆記。"
        "分類已由系統規則決定，禁止自行改分類；你只負責摘要、重點與下一步。"
        "只回 JSON,不要 markdown。格式:"
        '{"title":"短標題","summary":"80字內總結","what":"這是什麼","key_point":"關鍵重點",'
        '"action":"行動建議","detail_points":["3到6個重點"],"tags":["最多5個短標籤"]}'
        f"\n\ncategory:{classification.label}\nfolder:{classification.folder}\ncategory_reason:{classification.reason_text()}"
        f"\n\nsource_type:{source_type}\nraw:\n{raw_text[:6000]}"
    )


def call_gemini(raw_text: str, source_type: str, classification: Classification) -> LLMResult:
    if not settings.gemini_api_key:
        raise RuntimeError("missing GEMINI_API_KEY")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent"
    )
    resp = requests.post(
        url,
        params={"key": settings.gemini_api_key},
        json={"contents": [{"parts": [{"text": prompt(raw_text, source_type, classification)}]}]},
        timeout=35,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return parse_llm_json(text, "gemini", classification)


def call_deepseek(raw_text: str, source_type: str, classification: Classification) -> LLMResult:
    if not settings.deepseek_api_key:
        raise RuntimeError("missing DEEPSEEK_API_KEY")
    resp = requests.post(
        "https://api.deepseek.com/chat/completions",
        json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt(raw_text, source_type, classification)}],
            "temperature": 0.2,
        },
        headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
        timeout=35,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    return parse_llm_json(text, "deepseek", classification)


def organize(raw_text: str, source_type: str = "text") -> LLMResult:
    classification = classify(raw_text, source_type)
    if settings.dry_run:
        return LLMResult(
            title="乾跑測試收件",
            summary=f"這是一則 {source_type} 測試訊息，正式環境會由 Gemini 優先整理、DeepSeek 備援。",
            category=classification.label,
            folder=classification.folder,
            category_key=classification.key,
            category_reason=classification.reason_text(),
            what="LINE 測試訊息",
            key_point="正式環境會整理後寫入 Notion。",
            action="確認 LINE、Render、Notion 串接正常。",
            detail="這是 dry-run 測試內容。",
            tags=["dry-run"],
            provider="degraded",
            degraded=True,
        )
    try:
        return call_gemini(raw_text, source_type, classification)
    except Exception:
        pass
    try:
        return call_deepseek(raw_text, source_type, classification)
    except Exception:
        return fallback_result(raw_text, classification)
