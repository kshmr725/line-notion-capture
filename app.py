from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, request

from line_client import reply_text, verify_signature
from llm_router import organize
from notion_writer import create_capture_page

app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


def extract_text_event(event: dict[str, Any]) -> tuple[str, str, str]:
    message = event.get("message") or {}
    source = event.get("source") or {}
    source_user = source.get("userId") or source.get("groupId") or "unknown"
    message_id = message.get("id", "")
    msg_type = message.get("type", "unknown")
    if msg_type == "text":
        text = message.get("text", "")
        source_type = "url" if text.startswith(("http://", "https://")) else "text"
        return text, source_type, f"{source_user}:{message_id}"
    return f"[{msg_type}] message received. Content download is not enabled in MVP.", msg_type, f"{source_user}:{message_id}"


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
            raw_text, source_type, message_key = extract_text_event(event)
            reply_text(reply_token, "收到，正在整理到 Notion...")
            result = organize(raw_text, source_type)
            notion_url = create_capture_page(
                result=result,
                raw_input=raw_text,
                source_user=(event.get("source") or {}).get("userId", "unknown"),
                source_type=source_type,
                line_message_id=message_key,
            )
            done = f"已整理完成\n{result.title}\n分類:{result.category}"
            if notion_url:
                done += f"\n{notion_url}"
            reply_text(reply_token, done)
        except Exception as exc:
            reply_text(reply_token, f"已收到，但整理失敗，請稍後再試。\n{type(exc).__name__}")
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
