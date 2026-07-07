from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys

import requests


def sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def main() -> int:
    secret = os.getenv("LINE_CHANNEL_SECRET", "dry-run-secret")
    endpoint = os.getenv("SIMULATE_ENDPOINT", "http://127.0.0.1:8000/line/webhook")
    text = " ".join(sys.argv[1:]) or "朋友傳來一個測試想法：下週整理東京行程與餐廳清單"
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "dry-run-reply-token",
                "source": {"type": "user", "userId": "U_friend_demo"},
                "message": {"id": "M_demo_001", "type": "text", "text": text},
            }
        ]
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    resp = requests.post(endpoint, data=body, headers={"Content-Type": "application/json", "X-Line-Signature": sign(body, secret)}, timeout=20)
    print(resp.status_code)
    print(resp.text)
    return 0 if resp.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
