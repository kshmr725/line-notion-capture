# LINE Notion Capture Go-Live Runbook

這份文件只列真實上線流程，不含 dry-run demo。

## 已由 Codex 完成

- Production v1 程式碼完成
- SQLite 狀態追蹤與去重完成
- Notion database `LINE Capture Inbox` 已建立
- Notion database ID: `1b8c5d8e33cc416ca86f75e04cb15c40`
- Notion data source ID: `544d588a-ca4e-44af-86dc-f3ea85fba8ba`
- 已在 Notion database 建立真實驗收樣本: `[LIVE TEST] LINE OA 上線驗收樣本`
- 已建立 Notion Go-Live 控制頁: `LINE Notion Capture Go-Live 控制頁`

白話:Notion 端已經是真的。剩下是 LINE/Notion secret 這種必須你登入授權的步驟。

## 你本人必須完成的授權

LINE 官方文件要求 Messaging API 必須先有 LINE Official Account，並啟用 Messaging API。建立 OA 需要 Business ID、填表、登入 LINE Official Account Manager。

Notion API 需要 personal access token 或 internal connection token。token 只會顯示給 workspace 使用者本人，不能由 Codex 憑空產生。

## Step 1: 建立 LINE Official Account

打開:

```text
https://manager.line.biz/
```

操作:

1. 用你的 LINE Business ID 登入。
2. 建立新的 LINE Official Account。
3. 名稱建議: `Kevin Capture Bot` 或 `LINE Notion Capture`。
4. 建立後進入該 OA 後台。

白話:這一步會把朋友要加入的 LINE OA 建出來。

## Step 2: 啟用 Messaging API

在 LINE Official Account Manager:

1. 進入該 OA。
2. 找到 `Settings` / `設定`。
3. 找到 `Messaging API`。
4. 啟用 Messaging API。
5. 它會建立對應的 LINE Developers channel。

白話:沒有啟用 Messaging API，Render webhook 收不到 LINE 訊息。

## Step 3: 取得 LINE Developers 設定值

打開:

```text
https://developers.line.biz/console/
```

找到剛剛建立的 Messaging API channel。

需要複製:

```text
LINE_CHANNEL_SECRET=Channel secret
LINE_CHANNEL_ACCESS_TOKEN=Messaging API > Channel access token > Issue
```

白話:這兩個值是 Render 服務接 LINE 的鑰匙。

## Step 4: 建立 Notion Integration Token

打開:

```text
https://www.notion.so/profile/integrations
```

操作:

1. New integration / New token。
2. 名稱建議: `LINE Notion Capture`。
3. 選你的 workspace。
4. 複製 token，填入 Render 的 `NOTION_TOKEN`。

白話:這個 token 讓程式有權限把 LINE 資料寫進 Notion。

## Step 5: 分享 Notion Database 給 Integration

打開 database:

```text
https://app.notion.com/p/1b8c5d8e33cc416ca86f75e04cb15c40
```

操作:

1. 點右上角 Share。
2. Invite / Connect integration。
3. 選 `LINE Notion Capture` integration。

白話:只建立 token 不夠，還要把這個 database 明確分享給 integration。

## Step 6: Render 環境變數

在 Render service 填:

```text
LINE_CHANNEL_SECRET=貼 Channel secret
LINE_CHANNEL_ACCESS_TOKEN=貼 long-lived access token
GEMINI_API_KEY=貼 Gemini key
DEEPSEEK_API_KEY=貼 DeepSeek key
NOTION_TOKEN=貼 Notion integration token
NOTION_DATABASE_ID=1b8c5d8e33cc416ca86f75e04cb15c40
DATABASE_PATH=data/line-notion-capture.sqlite3
DRY_RUN=false
```

白話:正式上線一定要 `DRY_RUN=false`。

## Step 7: 設定 LINE Webhook URL

Render 部署後拿到服務網址，例如:

```text
https://line-notion-capture.onrender.com
```

在 LINE Developers channel 的 Messaging API 頁面設定:

```text
Webhook URL=https://line-notion-capture.onrender.com/line/webhook
Use webhook=Enabled
```

白話:這是 LINE 把朋友訊息送到你的服務的入口。

## Step 8: 驗收

本機或 Render shell 跑:

```bash
python scripts/verify_go_live.py https://你的-render-url
```

成功標準:

- Health check OK
- LINE token OK
- Notion token/database OK
- 手機加入 LINE OA 後傳一則文字
- Notion database 出現新資料

