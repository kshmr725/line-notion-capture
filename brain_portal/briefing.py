from __future__ import annotations

from typing import Sequence

from brain_portal.models import BriefingSection, BriefingSpec, CitedAnswer, SearchHit
from brain_portal.presentation import clean_display_text


def build_briefing(
    query: str,
    hits: Sequence[SearchHit],
    answer: CitedAnswer | None,
) -> BriefingSpec | None:
    """Build a source-grounded briefing without inventing unsupported claims."""
    if not hits:
        return None

    source_ids = tuple(hit.item.source_id for hit in hits)
    allowed = set(source_ids)
    safe_answer = answer if answer and set(answer.source_ids).issubset(allowed) else None
    answer_body = (
        safe_answer.text
        if safe_answer is not None
        else "目前沒有來源支持的摘要；以下只列出檢索到的原始證據。"
    )
    evidence_lines = [
        f"{clean_display_text(hit.item.title)}：{_summary(hit.item.summary, hit.item.body)}"
        for hit in hits[:5]
    ]
    evidence_body = "\n".join(f"• {line}" for line in evidence_lines)
    comparison_body = (
        f"本次整理 {len(hits)} 筆來源；結果依目前檢索排序呈現，"
        "不將來源缺少的欄位推論成事實。"
    )
    uncertainty_body = (
        "AI 摘要只使用有明確引用的來源。"
        if safe_answer is not None
        else "沒有可驗證的 AI 摘要，因此本頁不做未經來源支持的推論。"
    )
    sections = (
        BriefingSection("回答", answer_body, tuple(safe_answer.source_ids) if safe_answer else ()),
        BriefingSection("關鍵證據", evidence_body, source_ids),
        BriefingSection("比較", comparison_body, source_ids),
        BriefingSection("未確定事項", uncertainty_body, source_ids),
        BriefingSection("來源", "開啟下列來源查看原始內容與更新時間。", source_ids),
    )
    return BriefingSpec(
        title=f"{clean_display_text(query) or '知識'}研究摘要",
        query=clean_display_text(query),
        sections=sections,
        source_ids=source_ids,
        provider=safe_answer.provider if safe_answer is not None else None,
    )


def _summary(summary: str, body: str) -> str:
    text = clean_display_text(summary) or clean_display_text(body)
    return text[:240] if text else "來源未提供摘要。"
