from __future__ import annotations

from dataclasses import dataclass


AUTO_TEMPLATE = "auto"


@dataclass(frozen=True)
class FormatTemplate:
    key: str
    label: str
    description: str
    prompt_hint: str


TEMPLATES: dict[str, FormatTemplate] = {
    "auto": FormatTemplate(
        key="auto",
        label="自動判斷",
        description="系統依內容類型自動選擇最適合的筆記格式。",
        prompt_hint="先判斷內容類型，再選擇最適合的閱讀結構，不要把所有資料套成同一種格式。",
    ),
    "keep": FormatTemplate(
        key="keep",
        label="Keep 快速收藏",
        description="像 LINE Keep 一樣先保存，但補上摘要、用途與下一步。",
        prompt_hint="整理成快速收藏筆記：為什麼值得保存、核心摘要、可查找關鍵字、下一步。",
    ),
    "article": FormatTemplate(
        key="article",
        label="文章摘要",
        description="適合新聞、網頁、長文、研究資料。",
        prompt_hint="整理成文章摘要：TL;DR、主要論點、證據或數據、對讀者的意義、可採取行動。",
    ),
    "place": FormatTemplate(
        key="place",
        label="地點卡片",
        description="適合餐廳、咖啡廳、景點、Google Maps。",
        prompt_hint="整理成地點卡片：地址、時間、價位、特色、適合誰、何時去。未知欄位要寫資訊不足，不能編造。",
    ),
    "reading": FormatTemplate(
        key="reading",
        label="讀書筆記",
        description="適合書籍、閱讀清單、讀書心得。",
        prompt_hint="整理成讀書筆記：書/作者、核心概念、值得摘錄的觀點、目前進度或狀態、下一個閱讀行動。",
    ),
    "task": FormatTemplate(
        key="task",
        label="任務待辦",
        description="適合 todo、提醒、工作請求。",
        prompt_hint="整理成任務卡：要做什麼、負責人、期限、阻塞點、下一步。沒有提供的欄位寫資訊不足。",
    ),
    "custom": FormatTemplate(
        key="custom",
        label="自訂格式",
        description="使用者用「格式 自訂 ...」指定的整理規則。",
        prompt_hint="依使用者自訂格式整理；若自訂規則不足，保留原意並補上摘要、重點、下一步。",
    ),
}


ALIASES = {
    "自動": "auto",
    "auto": "auto",
    "keep": "keep",
    "收藏": "keep",
    "文章": "article",
    "article": "article",
    "地點": "place",
    "美食": "place",
    "place": "place",
    "讀書": "reading",
    "閱讀": "reading",
    "reading": "reading",
    "任務": "task",
    "待辦": "task",
    "task": "task",
    "自訂": "custom",
    "custom": "custom",
}


def normalize_template_key(value: str | None) -> str | None:
    key = (value or "").strip().lower()
    return ALIASES.get(key)


def get_template(key: str | None, custom_template: str = "") -> FormatTemplate:
    normalized = normalize_template_key(key) or "auto"
    if normalized == "custom" and custom_template.strip():
        return FormatTemplate(
            key="custom",
            label="自訂格式",
            description="使用者指定的整理規則。",
            prompt_hint=custom_template.strip()[:1200],
        )
    return TEMPLATES.get(normalized, TEMPLATES["auto"])


def choose_template(requested_key: str, category_key: str, source_type: str, custom_template: str = "") -> FormatTemplate:
    requested = normalize_template_key(requested_key) or "auto"
    if requested != "auto":
        return get_template(requested, custom_template)
    if category_key in {"food", "travel"}:
        return TEMPLATES["place"]
    if category_key == "reading":
        return TEMPLATES["reading"]
    if source_type == "url":
        return TEMPLATES["article"]
    return TEMPLATES["keep"]


def format_help(current_key: str = "auto", custom_template: str = "") -> str:
    current = get_template(current_key, custom_template)
    lines = [
        "目前整理格式：",
        f"🧩 {current.label}",
        "",
        "可以直接回覆：",
        "格式 自動",
        "格式 文章",
        "格式 地點",
        "格式 讀書",
        "格式 任務",
        "格式 收藏",
        "",
        "也可以自訂：",
        "格式 自訂 請整理成三段：背景、重點、我下一步要做什麼",
    ]
    return "\n".join(lines)
