from __future__ import annotations

from typing import Any

import time
from urllib.parse import urljoin

from flask import Flask, jsonify, render_template_string, request

from config import settings
from line_client import reply_text, verify_signature
from llm_router import organize
from notion_writer import create_capture_page

app = Flask(__name__)
app.config["DRY_RUN_VISIBLE"] = settings.dry_run


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/")
def dashboard():
    webhook_url = urljoin(request.host_url, "line/webhook")
    return render_template_string(
        DASHBOARD_HTML,
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


def process_message_event(event: dict[str, Any]) -> dict[str, str]:
    raw_text, source_type, message_key = extract_text_event(event)
    result = organize(raw_text, source_type)
    notion_url = create_capture_page(
        result=result,
        raw_input=raw_text,
        source_user=(event.get("source") or {}).get("userId", "unknown"),
        source_type=source_type,
        line_message_id=message_key,
    )
    return {
        "title": result.title,
        "category": result.category,
        "provider": result.provider,
        "notion_url": notion_url,
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
        try:
            reply_text(reply_token, "收到，正在整理到 Notion...")
            processed = process_message_event(event)
            done = f"已整理完成\n{processed['title']}\n分類:{processed['category']}\nAI:{processed['provider']}"
            if processed["notion_url"]:
                done += f"\n{processed['notion_url']}"
            reply_text(reply_token, done)
        except Exception as exc:
            reply_text(reply_token, f"已收到，但整理失敗，請稍後再試。\n{type(exc).__name__}")
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


DASHBOARD_HTML = """
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
  </main>
  <script>
    const button = document.querySelector("#send");
    const result = document.querySelector("#result");
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
      } catch (error) {
        result.textContent = String(error);
      } finally {
        button.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
