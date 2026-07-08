from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlparse


@dataclass(frozen=True)
class CategorySpec:
    key: str
    label: str
    folder: str
    icon: str
    cover_url: str
    visual_group: str
    domains: tuple[str, ...] = ()
    strong_keywords: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    priority: int = 0


@dataclass(frozen=True)
class Classification:
    key: str
    label: str
    folder: str
    icon: str
    cover_url: str
    visual_group: str
    confidence: str
    score: int
    reasons: tuple[str, ...]

    def reason_text(self) -> str:
        return " + ".join(self.reasons[:3]) or "default"


CATEGORY_SPECS: tuple[CategorySpec, ...] = (
    CategorySpec("daily", "日誌", "00_Daily_Notes_日誌", "📝", "https://images.unsplash.com/photo-1517842645767-c639042777db?auto=format&fit=crop&w=1400&q=80", "生活紀錄", keywords=("日記", "反思", "今天", "心情", "daily")),
    CategorySpec(
        "crypto",
        "加密貨幣",
        "10_Crypto_加密貨幣",
        "🪙",
        "https://images.unsplash.com/photo-1518546305927-5a555bb7020d?auto=format&fit=crop&w=1400&q=80",
        "市場資訊",
        domains=("coindesk.com", "cointelegraph.com", "decrypt.co", "theblock.co", "glassnode.com", "cryptoquant.com", "binance.com", "bybit.com"),
        strong_keywords=("bitcoin", "ethereum", "btc", "eth", "on-chain", "glassnode", "long-term holder", "accumulation"),
        keywords=("交易", "幣", "k線", "做多", "做空", "槓桿", "現貨", "期貨", "sol", "xrp"),
        priority=90,
    ),
    CategorySpec(
        "web3",
        "商業研究",
        "11_Web3_商業研究",
        "📊",
        "https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=1400&q=80",
        "研究資料",
        domains=("messari.io", "defillama.com", "a16zcrypto.com"),
        strong_keywords=("web3", "defi", "rwa", "depin", "tokenomics"),
        keywords=("nft", "區塊鏈研究", "研報", "代幣經濟", "白皮書"),
        priority=80,
    ),
    CategorySpec(
        "career",
        "求職與履歷",
        "20_Career_求職與履歷",
        "💼",
        "https://images.unsplash.com/photo-1497366811353-6870744d04b2?auto=format&fit=crop&w=1400&q=80",
        "人生任務",
        domains=("linkedin.com", "greenhouse.io", "lever.co", "indeed.com"),
        strong_keywords=("履歷", "面試", "職缺", "resume", "cv", "job", "interview", "offer"),
        keywords=("求職", "薪水", "獵頭", "職涯"),
        priority=70,
    ),
    CategorySpec("task", "任務待辦", "20_Tasks_任務待辦", "✅", "https://images.unsplash.com/photo-1484480974693-6ca0a78fb36b?auto=format&fit=crop&w=1400&q=80", "待處理", strong_keywords=("待辦", "todo", "提醒", "確認", "安排", "追蹤", "deadline", "買", "訂", "預算"), keywords=("要做", "幫我", "記得", "下一步", "任務", "task"), priority=100),
    CategorySpec("bd", "商務開發", "21_Business_Dev_商務開發", "🤝", "https://images.unsplash.com/photo-1556761175-b413da4baf72?auto=format&fit=crop&w=1400&q=80", "工作推進", keywords=("bd", "business development", "computex", "pitch", "客戶", "業務", "合作", "談判", "合約", "b2b")),
    CategorySpec("french", "法文學習", "30_Language_法文學習", "🇫🇷", "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?auto=format&fit=crop&w=1400&q=80", "學習資料", keywords=("french", "français", "tcf", "delf", "法文", "法語", "grammaire", "vocabulaire")),
    CategorySpec("immigration", "加拿大移民", "40_Immigration_加拿大移民", "🍁", "https://images.unsplash.com/photo-1517935706615-2717063c2225?auto=format&fit=crop&w=1400&q=80", "人生任務", keywords=("移民", "immigration", "whv", "working holiday", "express entry", "省提名", "簽證", "ircc", "lmia")),
    CategorySpec(
        "tech",
        "AI自動化",
        "50_Tech_AI自動化",
        "🤖",
        "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1400&q=80",
        "工具與自動化",
        domains=("github.com", "openai.com", "anthropic.com"),
        strong_keywords=("api", "automation", "claude", "gemini", "mcp", "自動化"),
        keywords=("cursor", "obsidian", "python", "prompt", "gpt", "ai tool", "n8n"),
        priority=40,
    ),
    CategorySpec("reading", "讀書筆記", "60_Reading_讀書筆記", "📚", "https://images.unsplash.com/photo-1519682337058-a94d519337bc?auto=format&fit=crop&w=1400&q=80", "閱讀收藏", keywords=("讀書", "閱讀", "書評", "認知", "心理學", "成長", "思維", "習慣", "book", "reading")),
    CategorySpec(
        "food",
        "美食與咖啡地圖",
        "71_Food_美食與咖啡地圖",
        "☕",
        "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?auto=format&fit=crop&w=1400&q=80",
        "地點地圖",
        domains=("maps.app.goo.gl", "maps.google.com"),
        strong_keywords=("google maps", "營業時間", "評價", "餐廳", "咖啡", "甜點"),
        keywords=("美食", "料理", "food", "酒", "拉麵", "探店", "菜單"),
        priority=60,
    ),
    CategorySpec("travel", "旅遊與行程", "72_Travel_旅遊與行程", "🧭", "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1400&q=80", "地點地圖", keywords=("旅遊", "travel", "景點", "行程", "出國", "機票", "飯店", "住宿", "遊記")),
    CategorySpec(
        "fitness",
        "健身與健康",
        "73_Fitness_健身與健康",
        "🥗",
        "https://images.unsplash.com/photo-1490645935967-10de6ba17061?auto=format&fit=crop&w=1400&q=80",
        "健康生活",
        domains=("who.int", "mayoclinic.org", "healthline.com"),
        strong_keywords=("healthy diet", "nutrition", "physical activity", "diabetes", "cardiovascular", "obesity"),
        keywords=("健身", "運動", "重訓", "飲食", "蛋白質", "熱量", "減脂", "增肌", "health", "diet", "healthy"),
        priority=55,
    ),
    CategorySpec("finance", "個人財務", "80_Finance_個人財務", "💰", "https://images.unsplash.com/photo-1554224155-6726b3ff858f?auto=format&fit=crop&w=1400&q=80", "財務整理", keywords=("記帳", "報稅", "稅務", "tax", "支出", "收入", "銀行", "信用卡", "保險", "budget", "預算", "資產配置")),
    CategorySpec("archive", "封存歸檔", "90_Archive_封存歸檔", "🗄️", "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=1400&q=80", "封存", keywords=("封存", "結案", "archive")),
)

DEFAULT_CLASSIFICATION = Classification(
    "inbox",
    "收件匣",
    "00_Inbox_收件匣",
    "📥",
    "https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1400&q=80",
    "快速收件",
    "low",
    0,
    ("default",),
)


def allowed_category_labels() -> set[str]:
    return {spec.label for spec in CATEGORY_SPECS} | {DEFAULT_CLASSIFICATION.label}


def classify(raw_text: str, source_type: str = "text") -> Classification:
    text = (raw_text or "").lower()
    domains = _extract_domains(raw_text)
    if _looks_like_task(text) and not any(_domain_matches(actual, "maps.google.com") or _domain_matches(actual, "maps.app.goo.gl") for actual in domains):
        task = _spec_by_key("task")
        return Classification(task.key, task.label, task.folder, task.icon, task.cover_url, task.visual_group, "high", 10, ("task intent",))
    best = DEFAULT_CLASSIFICATION
    best_priority = -1
    for spec in CATEGORY_SPECS:
        score = 0
        reasons: list[str] = []
        for domain in spec.domains:
            if any(_domain_matches(actual, domain) for actual in domains):
                score += 8
                reasons.append(domain)
                break
        for keyword in spec.strong_keywords:
            if _contains_keyword(text, keyword):
                score += 5
                reasons.append(keyword)
        for keyword in spec.keywords:
            if _contains_keyword(text, keyword):
                score += 2
                reasons.append(keyword)
        if score > best.score or (score == best.score and score > 0 and spec.priority > best_priority):
            best = Classification(spec.key, spec.label, spec.folder, spec.icon, spec.cover_url, spec.visual_group, _confidence(score), score, tuple(reasons[:5]))
            best_priority = spec.priority
    return best


def category_icon(category_key: str) -> str:
    return _spec_by_key(category_key).icon


def category_cover_url(category_key: str) -> str:
    return _spec_by_key(category_key).cover_url


def category_visual_group(category_key: str) -> str:
    return _spec_by_key(category_key).visual_group


def time_bucket(created_at) -> str:
    hour = created_at.hour
    if 5 <= hour < 12:
        return "早上"
    if 12 <= hour < 18:
        return "下午"
    if 18 <= hour < 23:
        return "晚上"
    return "深夜"


def _confidence(score: int) -> str:
    if score >= 8:
        return "high"
    if score >= 4:
        return "medium"
    return "low"


def _contains_keyword(text: str, keyword: str) -> bool:
    kw = keyword.strip().lower()
    if not kw:
        return False
    if re.fullmatch(r"[a-z0-9]{2,4}", kw):
        return re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text) is not None
    return kw in text


def _extract_domains(text: str) -> set[str]:
    domains = set()
    for url in re.findall(r"https?://[^\s<>)\]]+", text or "", flags=re.IGNORECASE):
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        if netloc:
            domains.add(netloc)
    return domains


def _domain_matches(actual_domain: str, rule_domain: str) -> bool:
    return actual_domain == rule_domain or actual_domain.endswith("." + rule_domain)


def _spec_by_key(key: str) -> CategorySpec:
    for spec in CATEGORY_SPECS:
        if spec.key == key:
            return spec
    return CategorySpec(
        DEFAULT_CLASSIFICATION.key,
        DEFAULT_CLASSIFICATION.label,
        DEFAULT_CLASSIFICATION.folder,
        DEFAULT_CLASSIFICATION.icon,
        DEFAULT_CLASSIFICATION.cover_url,
        DEFAULT_CLASSIFICATION.visual_group,
    )


def _looks_like_task(text: str) -> bool:
    task_words = ("待辦", "todo", "提醒", "確認", "安排", "追蹤", "deadline", "買", "訂", "預算", "要做", "幫我", "記得")
    if not any(word in text for word in task_words):
        return False
    place_only_words = ("google maps", "maps.app.goo.gl", "maps.google.com", "營業時間", "評價")
    return not any(word in text for word in place_only_words)
