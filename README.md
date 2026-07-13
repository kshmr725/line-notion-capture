# LINE Notion Capture

LINE 當入口,把使用者傳來的文字/網址交給 Gemini 優先整理,DeepSeek 備援,最後寫進 Notion database。

產品定位是「LINE Keep 的 AI 版」:使用者把資料丟給 LINE OA,系統依使用者指定的格式整理、分類,再寫進 Notion。Telegram+Obsidian 是私人工作流;這個專案是一般 user-facing 的 LINE+Notion 收件產品。

## 系統能力

- LINE webhook 簽章驗證
- 文字/網址訊息接收
- SQLite 入庫,保存每筆訊息處理狀態
- message key 去重,避免 LINE 重送造成 Notion 重複寫入
- Gemini 優先整理,DeepSeek 備援
- AI 全失敗時 degraded 保存原文
- 每位 LINE 使用者可設定預設整理格式
- 支援自動、文章、地點、讀書、任務、收藏與自訂格式
- Notion database properties + page body 同步寫入
- Notion Dashboard 復刻 My Dashboard 版型,並接上視覺圖庫、分類看板、時間段看板、收件日曆與收件總量
- 每筆 Notion 筆記可帶 icon、cover image、visual category、format、time bucket
- 使用者入口頁 `/`
- 瀏覽器管理頁 `/admin`
- 狀態 API `/api/status`
- 最近紀錄 API `/api/captures`
- dry-run 模式與 browser debug form

白話:這不是只會收一則訊息的 demo,而是一個有狀態、有去重、有格式偏好、有觀測頁的 production v1。

## 使用者在 LINE 裡怎麼用

一般使用:

```text
直接把文字、網址、想法、清單丟給 Kevin Capture
```

設定整理格式:

```text
設定
格式 自動
格式 文章
格式 地點
格式 讀書
格式 任務
格式 收藏
格式 自訂 請整理成三段：背景、重點、我下一步要做什麼
```

白話:使用者不用知道 webhook、Render、Notion API;他只要像用 LINE Keep 一樣丟資料,必要時用「格式」改整理樣式。

## 已建立的 Notion workspace

- Dashboard: https://app.notion.com/p/397ca826929a811cb2c1f7e35e09b372
- 舊版 Portal: https://app.notion.com/p/397ca826929a81b6aa12c04ce5c51168
- Database: `LINE Capture Inbox`
- Database ID: `1b8c5d8e33cc416ca86f75e04cb15c40`
- Data source ID: `544d588a-ca4e-44af-86dc-f3ea85fba8ba`

你仍需要在 Notion 建立一個 integration,取得 `NOTION_TOKEN`,並把 `LINE Capture Inbox` 分享給該 integration。

Dashboard 已依照使用者指定的 `My Dashboard` 模板重建:上方是 LINE Keep 式操作區,中段是格式分類說明,下方直接嵌入同一個 `LINE Capture Inbox` 的最新收件、視覺圖庫、分類看板、時間段看板、收件日曆與收件總量。舊版 Portal 保留作為 archive 與分類頁索引,頁首已加新版 Dashboard 連結。

新增的視覺欄位:

- `Visual Category`: 用圖示加主題群組做圖庫/看板分類
- `Cover Image`: 讓 gallery card 有封面圖
- `Icon`: 保留分類圖示,方便掃讀
- `Time Bucket`: 依收件時間分成早上、下午、晚上、深夜
- `Format`: 顯示這筆資料用文章、地點、讀書、任務或收藏哪種格式整理

白話:新的 Notion 不只是一張後台表格,而是能用封面、圖示、分類和時間去找資料的資料館。

## 本機啟動

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

## 免 token 乾跑驗證

先在 `.env` 設定:

```bash
LINE_CHANNEL_SECRET=dry-run-secret
DRY_RUN=true
```

啟動服務後,另開一個 terminal:

```bash
. .venv/bin/activate
python scripts/simulate_line_event.py "朋友傳來一個測試想法:下週整理東京行程"
```

預期:

- Terminal 看到 LINE dry-run 回覆
- Terminal 看到 Notion dry-run page
- 模擬 script 回 `200 {"status":"ok"}`

## 必填環境變數

```bash
LINE_CHANNEL_SECRET=
LINE_CHANNEL_ACCESS_TOKEN=
GEMINI_API_KEY=
DEEPSEEK_API_KEY=
NOTION_TOKEN=
NOTION_DATABASE_ID=1b8c5d8e33cc416ca86f75e04cb15c40
DATABASE_PATH=data/line-notion-capture.sqlite3
```

正式上線前要做:

1. 建 LINE Messaging API channel,取得 `LINE_CHANNEL_SECRET` 與 long-lived `LINE_CHANNEL_ACCESS_TOKEN`
2. 建 Notion integration,取得 `NOTION_TOKEN`
3. 把 `LINE Capture Inbox` database 分享給該 Notion integration
4. Render 部署本專案,填入以上環境變數
5. LINE Developers Console 的 webhook URL 設成 `https://你的 Render 網域/line/webhook`
6. 關掉 `DRY_RUN`

## LINE Webhook URL

部署後在 LINE Developers Console 設定:

```text
https://你的網域/line/webhook
```

## Render

本專案附 `render.yaml`,可直接建立 web service。Render 需要填上 `.env.example` 裡的 secret。

## Production v1 流程

1. 使用者傳 LINE 文字或網址
2. Webhook 驗證 LINE 簽章
3. 訊息寫入 SQLite,狀態為 `received`
4. 若同一個 message key 已完成,直接回覆既有 Notion URL
5. 狀態改為 `processing`
6. Gemini 整理
7. Gemini 失敗則 DeepSeek 備援
8. 兩者都失敗則以 `degraded` 保存原文
9. 寫入 Notion
10. SQLite 狀態改為 `completed`
11. Bot 先回「收到」,完成後用 LINE push 主動通知「已整理完成」
12. 失敗時 SQLite 狀態改為 `failed`,並保存錯誤訊息

## 待補到真正多使用者版

目前 production v1 使用一組全域 Notion token/database,適合先讓你和第一批朋友使用。若要變成每個人自己的 LINE Keep replacement,下一階段要補:

- 每位 LINE user 的 Notion OAuth 或安全 token 綁定
- 每位 user 自己的 Notion database / Portal
- 自訂格式規則的加密保存與管理頁
- LINE rich menu 或 LIFF 設定頁

白話:現在已經可以開始用,但還不是「每個朋友都接到自己的 Notion」的完整 SaaS 型態。

## LINE OA 回應設定

LINE Official Account Manager 的 `設定 -> 回應設定` 要關掉 `自動回應訊息` 與 `AI 回應訊息`,並開啟 `Webhook`。否則 LINE 會額外發出預設罐頭訊息,干擾真正的整理流程。

請不要使用 LINE OA 內建的 `AI 聊天機器人 (β)`。這個專案已經在 Render webhook 裡呼叫 Gemini/DeepSeek;如果再開 LINE 內建 AI,使用者會收到兩套系統的回覆,而且可能再次出現「本帳號無法個別回覆」這類 LINE 罐頭訊息。

建議檢查清單:

```text
Webhook: 開啟
自動回應訊息: 關閉
AI 回應訊息 / AI 聊天機器人: 關閉
歡迎訊息: 可保留,但只用來說明「傳資料給我,我會整理到 Notion」
```

白話:這條線是一般 user-facing 收件系統,不要和你的私人 Telegram+Obsidian 混在一起。

## 狀態欄位

SQLite `captures.status` 會出現:

- `received`:已收到但尚未整理
- `processing`:正在整理/寫入
- `completed`:已寫入 Notion
- `failed`:處理失敗,可在 `/api/captures` 看錯誤

白話:出問題時不用猜,先看 dashboard 或 API。

## Brain Cloud Portal(獨立唯讀服務)

`brain_portal/` + `portal_app.py` 是另一個獨立的 Flask 服務,不會動到上面的 LINE Notion Capture (`app.py`)。Obsidian 與 Notion 仍是正本,Portal 只讀不寫。

本機啟動:

```bash
. .venv/bin/activate
PORTAL_TENANT_ID=kevin PORTAL_DATABASE_PATH=data/brain-portal.sqlite3 \
  flask --app portal_app run --port 5050
```

本機索引(擇一來源):

```bash
# 從 Obsidian vault 索引
python scripts/index_brain_portal.py --tenant kevin \
  --obsidian-root ~/Desktop/Kevin_Brain --database data/brain-portal.sqlite3

# 先乾跑,只看會索引幾筆,不寫入資料庫
python scripts/index_brain_portal.py --tenant kevin \
  --obsidian-root ~/Desktop/Kevin_Brain --dry-run

# 從 Notion guided database 索引
python scripts/index_brain_portal.py --tenant kevin \
  --notion-connection <Notion database id> --database data/brain-portal.sqlite3
```

索引需要 `GEMINI_API_KEY` 才能產生 embedding;沒有設定會直接失敗並回傳非 0 exit code,不會半途寫入不完整的向量。

驗證資料完整性:

```bash
python scripts/verify_brain_portal.py --tenant kevin --database data/brain-portal.sqlite3
```

輸出是 JSON,包含 `tenant_leaks`、`missing_canonical_refs`、`unsafe_canonical_refs`、`embedding_spaces`、`stale_syncs`、`uncited_cached_answers` 與整體 `valid`。任何一項不乾淨,`valid` 就是 `false` 且 exit code 非 0,適合放進排程或 CI 檢查。

Stale 復原:

1. 跑 `verify_brain_portal.py`,若 `stale_syncs` 非空,代表最近一次來源掃描失敗,Portal 仍安全地保留上一次成功的投影,不會顯示半套資料。
2. 修好來源問題(例如 Obsidian vault 路徑、Notion token 權限)後,重新執行 `index_brain_portal.py`。
3. 再跑一次 `verify_brain_portal.py`,`stale_syncs` 應該清空、`valid` 回到 `true`。

Rollback:

- Portal 資料庫是唯讀投影,可直接刪除 `PORTAL_DATABASE_PATH` 指到的 SQLite 檔案後重新索引,不影響 Obsidian 或 Notion 正本。
- Render 上的 `brain-cloud-portal` service 與 `line-notion-capture` 是分開部署,回滾其中一個不會影響另一個。

白話:Portal 出問題最壞情況就是刪掉投影資料庫重建,原始資料永遠在 Obsidian/Notion,不會遺失。
