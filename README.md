# LINE Notion Capture

LINE 當入口,把使用者傳來的文字/網址交給 Gemini 優先整理,DeepSeek 備援,最後寫進 Notion database。

## 已建立的 Notion database

- Database: `LINE Capture Inbox`
- Database ID: `1b8c5d8e33cc416ca86f75e04cb15c40`
- Data source ID: `544d588a-ca4e-44af-86dc-f3ea85fba8ba`

你仍需要在 Notion 建立一個 integration,取得 `NOTION_TOKEN`,並把 `LINE Capture Inbox` 分享給該 integration。

## 本機啟動

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

## 必填環境變數

```bash
LINE_CHANNEL_SECRET=
LINE_CHANNEL_ACCESS_TOKEN=
GEMINI_API_KEY=
DEEPSEEK_API_KEY=
NOTION_TOKEN=
NOTION_DATABASE_ID=1b8c5d8e33cc416ca86f75e04cb15c40
```

## LINE Webhook URL

部署後在 LINE Developers Console 設定:

```text
https://你的網域/line/webhook
```

## Render

本專案附 `render.yaml`,可直接建立 web service。Render 需要填上 `.env.example` 裡的 secret。

## MVP 流程

1. 使用者傳 LINE 文字或網址
2. Bot 回「收到，正在整理到 Notion...」
3. Gemini 整理
4. Gemini 失敗則 DeepSeek 備援
5. 兩者都失敗則以 `degraded` 保存原文
6. 寫入 Notion
7. Bot 回「已整理完成」

白話:這條線是一般 user-facing 收件系統,不要和你的私人 Telegram+Obsidian 混在一起。
