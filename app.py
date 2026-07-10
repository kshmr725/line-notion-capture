from __future__ import annotations

from typing import Any

import time
from urllib.parse import quote, urljoin

from flask import Flask, jsonify, render_template_string, request

import capture_store
from config import settings
from format_templates import format_help, get_template, normalize_template_key
from line_client import push_text, reply_text, verify_signature
from llm_router import organize
from notion_writer import create_capture_page
import user_store

app = Flask(__name__)
app.config["DRY_RUN_VISIBLE"] = settings.dry_run


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/status")
def api_status():
    return jsonify({"status": "ok", "dry_run": bool(app.config.get("DRY_RUN_VISIBLE")), "stats": capture_store.stats()})


@app.get("/api/captures")
def api_captures():
    records = capture_store.list_recent(limit=int(request.args.get("limit", 25)))
    return jsonify(
        {
            "captures": [
                {
                    "id": record.id,
                    "message_key": record.message_key,
                    "source_user": record.source_user,
                    "source_type": record.source_type,
                    "status": record.status,
                    "title": record.title,
                    "category": record.category,
                    "provider": record.provider,
                    "notion_url": record.notion_url,
                    "error": record.error,
                    "duplicate_count": record.duplicate_count,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                }
                for record in records
            ]
        }
    )


@app.get("/")
def landing():
    add_line_url = "https://line.me/R/ti/p/@658husbm"
    notion_url = "https://app.notion.com/p/397ca826929a811cb2c1f7e35e09b372"
    return render_template_string(
        LANDING_HTML,
        add_line_url=add_line_url,
        notion_url=notion_url,
        qr_url=f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={quote(add_line_url, safe='')}",
    )


@app.get("/admin")
def dashboard():
    webhook_url = urljoin(request.host_url, "line/webhook")
    return render_template_string(
        ADMIN_DASHBOARD_HTML,
        dry_run="ON" if app.config.get("DRY_RUN_VISIBLE") else "OFF",
        webhook_url=webhook_url,
    )


def extract_text_event(event: dict[str, Any]) -> tuple[str, str, str]:
    message = event.get("message") or {}
    source = event.get("source") or {}
    source_user = source.get("userId") or source.get("groupId") or "unknown"
    message_id = message.get("id", "")
    msg_type = message.get("type", "unknown")
    if msg_type == "text":
        text = message.get("text", "")
        source_type = "url" if "http://" in text or "https://" in text else "text"
        return text, source_type, f"{source_user}:{message_id}"
    return f"[{msg_type}] message received. Content download is not enabled in MVP.", msg_type, f"{source_user}:{message_id}"


def source_user_from_event(event: dict[str, Any]) -> str:
    source = event.get("source") or {}
    return source.get("userId") or source.get("groupId") or source.get("roomId") or "unknown"


def handle_text_command(text: str, source_user: str) -> str | None:
    stripped = (text or "").strip()
    lowered = stripped.lower()
    preference = user_store.get_or_create(source_user)
    if lowered in {"help", "說明", "幫助", "設定", "格式"}:
        return (
            "Kevin Capture 可以像 LINE Keep 一樣收資料，並整理到 Notion。\n\n"
            f"{format_help(preference.default_template, preference.custom_template)}"
        )
    if lowered.startswith("格式 "):
        payload = stripped.split(maxsplit=1)[1].strip()
        if payload.startswith("自訂 "):
            custom = payload.split(maxsplit=1)[1].strip()
            if not custom:
                return "請在「格式 自訂」後面寫你想要的整理規則。"
            preference = user_store.set_template(source_user, "custom", custom)
            template = get_template(preference.default_template, preference.custom_template)
            return f"已更新整理格式：{template.label}\n\n之後你丟進來的資料會照這個規則整理：\n{preference.custom_template}"
        template_key = normalize_template_key(payload)
        if not template_key:
            return format_help(preference.default_template, preference.custom_template)
        preference = user_store.set_template(source_user, template_key)
        template = get_template(preference.default_template, preference.custom_template)
        return f"已更新整理格式：{template.label}\n\n{template.description}"
    return None


def process_message_event(event: dict[str, Any]) -> dict[str, str]:
    raw_text, source_type, message_key = extract_text_event(event)
    source_user = source_user_from_event(event)
    preference = user_store.get_or_create(source_user)
    record, created = capture_store.record_inbound(
        message_key=message_key,
        source_user=source_user,
        source_type=source_type,
        raw_input=raw_text,
        payload=event,
    )
    if not created and record.status == "completed":
        return {
            "title": record.title,
            "category": record.category,
            "provider": record.provider,
            "template": "",
            "notion_url": record.notion_url,
            "status": "duplicate_completed",
        }
    capture_store.mark_processing(message_key)
    result = organize(
        raw_text,
        source_type,
        template_key=preference.default_template,
        custom_template=preference.custom_template,
    )
    notion_url = create_capture_page(
        result=result,
        raw_input=raw_text,
        source_user=source_user,
        source_type=source_type,
        line_message_id=message_key,
    )
    capture_store.mark_completed(
        message_key=message_key,
        title=result.title,
        category=result.category,
        provider=result.provider,
        notion_url=notion_url,
    )
    return {
        "title": result.title,
        "category": result.category,
        "provider": result.provider,
        "template": result.template_label,
        "notion_url": notion_url,
        "status": "completed",
    }


@app.post("/line/webhook")
def line_webhook():
    body = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")
    if not verify_signature(body, signature):
        return jsonify({"error": "invalid LINE signature"}), 401
    payload = request.get_json(silent=True) or {}
    for event in payload.get("events", []):
        if event.get("type") != "message":
            continue
        reply_token = event.get("replyToken", "")
        source_user = source_user_from_event(event)
        try:
            raw_text, source_type, _ = extract_text_event(event)
            if source_type == "text":
                command_reply = handle_text_command(raw_text, source_user)
                if command_reply:
                    reply_text(reply_token, command_reply)
                    continue
            reply_text(reply_token, "收到，我正在整理成你的 Notion 筆記。完成後會把連結傳給你。")
            processed = process_message_event(event)
            prefix = "這則已整理過" if processed["status"] == "duplicate_completed" else "已整理完成"
            template_line = (
                "\n🧩 格式：沿用原筆記"
                if processed["status"] == "duplicate_completed"
                else f"\n🧩 格式：{processed.get('template') or 'Keep 快速收藏'}"
            )
            done = (
                f"✅ {prefix}\n\n📌 {processed['title']}"
                f"\n📂 分類：{processed['category']}"
                f"{template_line}"
            )
            if processed["notion_url"]:
                done += f"\n\n打開筆記：\n{processed['notion_url']}"
            push_text(source_user, done)
        except Exception as exc:
            try:
                _, _, message_key = extract_text_event(event)
                capture_store.mark_failed(message_key, f"{type(exc).__name__}: {exc}")
            except Exception:
                pass
            push_text(source_user, f"⚠️ 已收到，但整理失敗，請稍後再試。\n{type(exc).__name__}")
    return jsonify({"status": "ok"})


@app.post("/debug/simulate")
def debug_simulate():
    if not app.config.get("DRY_RUN_VISIBLE"):
        return jsonify({"error": "debug simulation is available only when DRY_RUN=true"}), 403
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "").strip()
    user_id = str(data.get("user_id") or "U_browser_demo").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400
    event = {
        "type": "message",
        "source": {"type": "user", "userId": user_id},
        "message": {"id": f"M_browser_{int(time.time())}", "type": "text", "text": text},
    }
    return jsonify({"status": "ok", "result": process_message_event(event)})


LANDING_HTML = """
<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kevin Capture</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f2ed;
      --ink: #202124;
      --muted: #68645d;
      --line: #d7d1c5;
      --paper: #fffdf8;
      --accent: #0f8f5f;
      --accent-dark: #0a6f4a;
      --soft: #e5f3ec;
      --amber: #f4df9c;
      --blue: #d9e7f7;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--ink); }
    a { color: inherit; }
    .wrap { width: min(1120px, calc(100% - 32px)); margin: 0 auto; }
    header { padding: 18px 0; border-bottom: 1px solid var(--line); background: rgba(244, 242, 237, .92); position: sticky; top: 0; z-index: 2; }
    nav { display: flex; align-items: center; justify-content: space-between; gap: 18px; }
    .brand { display: flex; align-items: center; gap: 10px; font-weight: 760; }
    .mark { width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center; background: #121212; color: #fff; }
    .navlinks { display: flex; align-items: center; gap: 10px; }
    .btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-height: 44px; padding: 0 16px; border-radius: 12px; border: 1px solid var(--line); text-decoration: none; font-weight: 700; white-space: nowrap; }
    .btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
    .btn.primary:hover { background: var(--accent-dark); }
    .hero { display: grid; grid-template-columns: minmax(0, 1.1fr) 360px; gap: 42px; align-items: center; padding: 64px 0 44px; }
    h1 { margin: 0; font-size: clamp(40px, 6vw, 72px); line-height: .98; letter-spacing: 0; max-width: 760px; }
    .lead { max-width: 620px; margin: 22px 0 0; color: var(--muted); font-size: 19px; line-height: 1.55; }
    .hero-actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 28px; }
    .qr-card { background: var(--paper); border: 1px solid var(--line); border-radius: 18px; padding: 22px; box-shadow: 0 16px 48px rgba(45, 40, 30, .08); }
    .qr-card img { display: block; width: 220px; height: 220px; margin: 0 auto; border-radius: 12px; }
    .qr-card strong { display: block; margin-top: 16px; font-size: 18px; }
    .qr-card p { margin: 8px 0 0; color: var(--muted); line-height: 1.5; }
    .band { margin: 20px 0 52px; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
    .step, .format, .note { background: var(--paper); border: 1px solid var(--line); border-radius: 16px; padding: 18px; }
    .step b, .format b { display: block; margin-bottom: 8px; }
    .step p, .format p, .note p { margin: 0; color: var(--muted); line-height: 1.55; }
    section { padding: 20px 0 44px; }
    h2 { font-size: clamp(28px, 4vw, 44px); margin: 0 0 16px; letter-spacing: 0; }
    .formats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
    .format { min-height: 156px; }
    .format .icon { font-size: 30px; margin-bottom: 14px; }
    .format:nth-child(1) { background: var(--soft); }
    .format:nth-child(2) { background: #fff7dd; }
    .format:nth-child(3) { background: var(--blue); }
    .format:nth-child(4) { background: #f2e8ff; }
    .sample { display: grid; grid-template-columns: .95fr 1.05fr; gap: 18px; align-items: stretch; margin-top: 18px; }
    .phone, .notion { border: 1px solid var(--line); border-radius: 18px; background: var(--paper); padding: 20px; }
    .bubble { max-width: 92%; border-radius: 18px; padding: 13px 15px; margin: 10px 0; line-height: 1.5; }
    .bubble.me { margin-left: auto; background: #d8f7ce; }
    .bubble.bot { background: #f0eee9; }
    .notion-row { display: grid; grid-template-columns: 42px 1fr; gap: 12px; align-items: start; border-top: 1px solid var(--line); padding-top: 14px; margin-top: 14px; }
    .tile-icon { width: 42px; height: 42px; border-radius: 12px; display: grid; place-items: center; background: var(--soft); font-size: 24px; }
    footer { border-top: 1px solid var(--line); padding: 24px 0 36px; color: var(--muted); }
    @media (max-width: 860px) {
      header { position: static; }
      nav { align-items: flex-start; }
      .navlinks { flex-direction: column; align-items: stretch; }
      .hero, .sample { grid-template-columns: 1fr; }
      .band, .formats { grid-template-columns: 1fr; }
      .qr-card img { width: 190px; height: 190px; }
    }
  </style>
</head>
<body>
  <header>
    <nav class="wrap">
      <div class="brand"><span class="mark">KC</span><span>Kevin Capture</span></div>
      <div class="navlinks">
        <a class="btn" href="{{ notion_url }}" target="_blank" rel="noreferrer">打開資料庫</a>
        <a class="btn primary" href="{{ add_line_url }}" target="_blank" rel="noreferrer">加入 LINE</a>
      </div>
    </nav>
  </header>
  <main class="wrap">
    <section class="hero">
      <div>
        <h1>把 LINE 當成會整理的 Keep</h1>
        <p class="lead">丟網址、文字、想法或待辦進來。系統會整理成你的格式，分類放進 Notion。</p>
        <div class="hero-actions">
          <a class="btn primary" href="{{ add_line_url }}" target="_blank" rel="noreferrer">加入 Kevin Capture</a>
          <a class="btn" href="{{ notion_url }}" target="_blank" rel="noreferrer">看 Notion 入口</a>
        </div>
      </div>
      <aside class="qr-card">
        <img src="{{ qr_url }}" alt="加入 Kevin Capture 的 LINE QR code">
        <strong>LINE ID：@658husbm</strong>
        <p>掃碼或按加入。傳一則訊息後，完成時會收到 Notion 筆記連結。</p>
      </aside>
    </section>
    <div class="band">
      <div class="step"><b>1. 傳進 LINE</b><p>像用 Keep 一樣，不用先想分類。</p></div>
      <div class="step"><b>2. 自動整理</b><p>依內容選文章、地點、讀書、任務或快速收藏。</p></div>
      <div class="step"><b>3. 回到 Notion</b><p>每筆資料有分類、摘要、下一步和入口連結。</p></div>
    </div>
    <section>
      <h2>資料會長成不同卡片</h2>
      <div class="formats">
        <div class="format"><div class="icon">🧾</div><b>文章摘要</b><p>新聞、研究、網頁整理成重點、證據和行動建議。</p></div>
        <div class="format"><div class="icon">☕</div><b>地點卡片</b><p>餐廳、咖啡、景點優先看地址、時間、價位和適合情境。</p></div>
        <div class="format"><div class="icon">📚</div><b>讀書筆記</b><p>書籍、影片或學習資料保留核心概念與閱讀進度。</p></div>
        <div class="format"><div class="icon">✅</div><b>任務待辦</b><p>買東西、訂位、確認預算會被整理成可執行事項。</p></div>
      </div>
    </section>
    <section>
      <h2>實際使用感</h2>
      <div class="sample">
        <div class="phone">
          <div class="bubble me">幫我記：週末找台北安靜咖啡廳，適合討論專案，預算每人 300 內。</div>
          <div class="bubble bot">收到，我正在整理成你的 Notion 筆記。完成後會把連結傳給你。</div>
          <div class="bubble bot">✅ 已整理完成<br><br>📌 週末台北咖啡廳清單<br>📂 分類：美食與咖啡地圖<br>🧩 格式：地點卡片</div>
        </div>
        <div class="notion">
          <strong>Notion 裡會看到</strong>
          <div class="notion-row">
            <div class="tile-icon">☕</div>
            <div><b>週末台北咖啡廳清單</b><p>分類：地點地圖。重點：安靜、可討論、預算 300 內。下一步：挑 3 家並確認營業時間。</p></div>
          </div>
          <div class="notion-row">
            <div class="tile-icon">✅</div>
            <div><b>生日禮物與訂位待辦</b><p>分類：待處理。重點：買禮物、訂餐廳、確認預算。下一步：今天先確定預算上限。</p></div>
          </div>
        </div>
      </div>
    </section>
    <section class="note">
      <b>可以自己改格式</b>
      <p>在 LINE 傳「格式 文章」「格式 地點」「格式 任務」即可切換。也可以傳「格式 自訂 請整理成背景、重點、下一步」。</p>
    </section>
  </main>
  <footer>
    <div class="wrap">Kevin Capture 會把你傳入的資料整理到已連接的 Notion。朋友使用前，請先確認資料要進哪個 Notion workspace。</div>
  </footer>
</body>
</html>
"""


ADMIN_DASHBOARD_HTML = """
<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LINE Notion Capture</title>
  <style>
    :root { color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #f7f5ef; color: #1d1d1f; }
    main { max-width: 880px; margin: 0 auto; padding: 48px 24px; }
    h1 { margin: 0 0 8px; font-size: 34px; letter-spacing: 0; }
    p { line-height: 1.65; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin-top: 24px; }
    .panel { background: #fff; border: 1px solid #dedad1; border-radius: 8px; padding: 18px; }
    .warning { border-color: #e5b66c; background: #fff7e6; }
    .checklist { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
    .checklist li { display: grid; grid-template-columns: 34px 1fr; gap: 10px; align-items: start; padding: 10px; border: 1px solid #eadfcf; border-radius: 8px; background: #fff; }
    .badge { width: 28px; height: 28px; border-radius: 999px; display: grid; place-items: center; font-weight: 800; }
    .on { background: #dff6e6; color: #126b35; }
    .off { background: #ffe2dc; color: #9b2718; }
    .muted { color: #6f685d; font-size: 14px; }
    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; }
    .stat { border: 1px solid #e5ded2; border-radius: 8px; padding: 12px; background: #fbfaf7; }
    .stat strong { display: block; font-size: 24px; margin-top: 4px; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td { border-bottom: 1px solid #e5ded2; padding: 9px 6px; text-align: left; vertical-align: top; }
    th { color: #6f685d; font-weight: 650; }
    .scroll { overflow-x: auto; }
    code { background: #eee8dc; padding: 2px 5px; border-radius: 4px; word-break: break-all; }
    label { display: block; font-weight: 650; margin: 14px 0 6px; }
    input, textarea { width: 100%; box-sizing: border-box; border: 1px solid #cfc8ba; border-radius: 6px; padding: 10px; font: inherit; }
    textarea { min-height: 120px; resize: vertical; }
    button { margin-top: 12px; border: 0; border-radius: 6px; background: #1f6feb; color: #fff; padding: 10px 14px; font: inherit; cursor: pointer; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    pre { white-space: pre-wrap; background: #1d1d1f; color: #f7f5ef; border-radius: 8px; padding: 14px; min-height: 72px; }
  </style>
</head>
<body>
  <main>
    <h1>LINE Notion Capture</h1>
    <p>LINE 訊息進來後，系統會呼叫 AI 整理，再寫入 Notion database。</p>
    <div class="grid">
      <section class="panel">
        <h2>狀態</h2>
        <p>DRY_RUN: <code>{{ dry_run }}</code></p>
        <p>Webhook URL:<br><code>{{ webhook_url }}</code></p>
        <div class="stats" id="stats"></div>
      </section>
      <section class="panel warning">
        <h2>LINE OA 回覆檢查</h2>
        <p class="muted">如果使用者看到「很抱歉，本帳號無法個別回覆用戶的訊息」，那是 LINE OA 後台自動訊息，不是這個 Render webhook 發的。</p>
        <ul class="checklist">
          <li><span class="badge on">開</span><div><b>Webhook</b><br><span class="muted">設定 -> 回應設定 -> Webhook 必須啟用。</span></div></li>
          <li><span class="badge off">關</span><div><b>自動回應訊息</b><br><span class="muted">必須關閉，否則 LINE 會插入罐頭回覆。</span></div></li>
          <li><span class="badge off">關</span><div><b>AI 聊天機器人 / AI 回應訊息</b><br><span class="muted">不要建立、不要啟用；Gemini/DeepSeek 已經由本系統處理。</span></div></li>
          <li><span class="badge off">關</span><div><b>聊天室手動接待插話</b><br><span class="muted">若還出現罐頭訊息，請到「聊天 / 回應設定」確認沒有手動接待或無法回覆訊息在作用。</span></div></li>
        </ul>
      </section>
      <section class="panel">
        <h2>Browser Dry Run</h2>
        <label for="user_id">LINE user id</label>
        <input id="user_id" value="U_browser_demo">
        <label for="text">訊息內容</label>
        <textarea id="text">朋友傳來：幫我整理一個週末台北咖啡廳清單，適合聊天和討論專案。</textarea>
        <button id="send">送出模擬訊息</button>
      </section>
    </div>
    <h2>結果</h2>
    <pre id="result">尚未送出</pre>
    <h2>最近紀錄</h2>
    <section class="panel scroll">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Status</th>
            <th>Title</th>
            <th>Category</th>
            <th>Provider</th>
            <th>Dup</th>
          </tr>
        </thead>
        <tbody id="captures"></tbody>
      </table>
    </section>
  </main>
  <script>
    const button = document.querySelector("#send");
    const result = document.querySelector("#result");
    const stats = document.querySelector("#stats");
    const captures = document.querySelector("#captures");
    async function refreshStatus() {
      const [statusResponse, capturesResponse] = await Promise.all([
        fetch("/api/status"),
        fetch("/api/captures?limit=12")
      ]);
      const statusData = await statusResponse.json();
      const capturesData = await capturesResponse.json();
      stats.innerHTML = Object.entries(statusData.stats).map(([key, value]) =>
        `<div class="stat">${key}<strong>${value}</strong></div>`
      ).join("");
      captures.innerHTML = capturesData.captures.map((row) =>
        `<tr>
          <td>${row.id}</td>
          <td>${row.status}</td>
          <td>${row.title || "(pending)"}</td>
          <td>${row.category || ""}</td>
          <td>${row.provider || ""}</td>
          <td>${row.duplicate_count}</td>
        </tr>`
      ).join("");
    }
    button.addEventListener("click", async () => {
      button.disabled = true;
      result.textContent = "送出中...";
      try {
        const response = await fetch("/debug/simulate", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            user_id: document.querySelector("#user_id").value,
            text: document.querySelector("#text").value
          })
        });
        const data = await response.json();
        result.textContent = JSON.stringify(data, null, 2);
        await refreshStatus();
      } catch (error) {
        result.textContent = String(error);
      } finally {
        button.disabled = false;
      }
    });
    refreshStatus().catch((error) => { result.textContent = String(error); });
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
