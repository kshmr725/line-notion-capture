from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any

import requests

from config import settings


LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


def verify_signature(body: bytes, signature: str, secret: str | None = None) -> bool:
    secret = secret if secret is not None else settings.line_channel_secret
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def reply_text(reply_token: str, text: str) -> None:
    if settings.dry_run:
        print(f"[LINE DRY RUN reply] {text}")
        return
    if not settings.line_channel_access_token or not reply_token:
        return
    payload: dict[str, Any] = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text[:4900]}],
    }
    resp = requests.post(
        LINE_REPLY_URL,
        json=payload,
        headers={"Authorization": f"Bearer {settings.line_channel_access_token}"},
        timeout=20,
    )
    resp.raise_for_status()


def push_text(user_id: str, text: str) -> None:
    if settings.dry_run:
        print(f"[LINE DRY RUN push] {user_id}: {text}")
        return
    if not settings.line_channel_access_token or not user_id:
        return
    payload: dict[str, Any] = {
        "to": user_id,
        "messages": [{"type": "text", "text": text[:4900]}],
    }
    resp = requests.post(
        LINE_PUSH_URL,
        json=payload,
        headers={"Authorization": f"Bearer {settings.line_channel_access_token}"},
        timeout=20,
    )
    resp.raise_for_status()
