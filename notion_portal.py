from __future__ import annotations

from dataclasses import dataclass


PORTAL_PAGE_ID = "397ca826-929a-81b6-aa12-c04ce5c51168"
PORTAL_URL = "https://app.notion.com/p/397ca826929a81b6aa12c04ce5c51168"


@dataclass(frozen=True)
class PortalPage:
    title: str
    page_id: str
    url: str


CATEGORY_PAGES: dict[str, PortalPage] = {
    "inbox": PortalPage(
        "📥 00 收件匣",
        "397ca826-929a-81e0-8012-ef9323954ad8",
        "https://app.notion.com/p/397ca826929a81e08012ef9323954ad8",
    ),
    "daily": PortalPage(
        "🗓️ 00 日誌",
        "397ca826-929a-81ef-a79f-f56c51e038b2",
        "https://app.notion.com/p/397ca826929a81efa79ff56c51e038b2",
    ),
    "crypto": PortalPage(
        "🪙 10 加密貨幣",
        "397ca826-929a-81db-98f7-d5fa550eae8d",
        "https://app.notion.com/p/397ca826929a81db98f7d5fa550eae8d",
    ),
    "web3": PortalPage(
        "🧪 11 Web3 商業研究",
        "397ca826-929a-815f-b0af-df3e368fd244",
        "https://app.notion.com/p/397ca826929a815fb0afdf3e368fd244",
    ),
    "career": PortalPage(
        "💼 20 求職與履歷",
        "397ca826-929a-81ac-b7d9-e75578d68606",
        "https://app.notion.com/p/397ca826929a81acb7d9e75578d68606",
    ),
    "bd": PortalPage(
        "🤝 21 商務開發",
        "397ca826-929a-8140-b0b5-dc40b6c0729f",
        "https://app.notion.com/p/397ca826929a8140b0b5dc40b6c0729f",
    ),
    "french": PortalPage(
        "🇫🇷 30 法文學習",
        "397ca826-929a-81cd-a106-f6bfc4569015",
        "https://app.notion.com/p/397ca826929a81cda106f6bfc4569015",
    ),
    "immigration": PortalPage(
        "🇨🇦 40 加拿大移民",
        "397ca826-929a-819d-9850-e3ebe92658d3",
        "https://app.notion.com/p/397ca826929a819d9850e3ebe92658d3",
    ),
    "tech": PortalPage(
        "🤖 50 AI 自動化",
        "397ca826-929a-81e4-9076-ca79f09d1aaa",
        "https://app.notion.com/p/397ca826929a81e49076ca79f09d1aaa",
    ),
    "reading": PortalPage(
        "📚 60 讀書筆記",
        "397ca826-929a-81e9-9280-c60b1e420a9e",
        "https://app.notion.com/p/397ca826929a81e99280c60b1e420a9e",
    ),
    "food": PortalPage(
        "☕ 71 美食與咖啡地圖",
        "397ca826-929a-8135-af62-c747f6a34dfb",
        "https://app.notion.com/p/397ca826929a8135af62c747f6a34dfb",
    ),
    "travel": PortalPage(
        "✈️ 72 旅遊與行程",
        "397ca826-929a-8191-8890-e9d4c96ea899",
        "https://app.notion.com/p/397ca826929a81918890e9d4c96ea899",
    ),
    "fitness": PortalPage(
        "🏋️ 73 健身與健康",
        "397ca826-929a-81c6-bc77-e0b4bc50ab6b",
        "https://app.notion.com/p/397ca826929a81c6bc77e0b4bc50ab6b",
    ),
    "finance": PortalPage(
        "💰 80 個人財務",
        "397ca826-929a-81da-b1bb-e4dae6146d98",
        "https://app.notion.com/p/397ca826929a81dab1bbe4dae6146d98",
    ),
    "archive": PortalPage(
        "🗄️ 90 封存歸檔",
        "397ca826-929a-81e7-96ff-f81f98c922e7",
        "https://app.notion.com/p/397ca826929a81e796fff81f98c922e7",
    ),
}


def category_page_for(key: str) -> PortalPage:
    return CATEGORY_PAGES.get(key) or CATEGORY_PAGES["inbox"]
