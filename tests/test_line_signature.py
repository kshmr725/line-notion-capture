import base64
import hashlib
import hmac

from line_client import verify_signature
import line_client


def test_verify_signature_valid():
    body = b'{"events":[]}'
    secret = "test-secret"
    signature = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    assert verify_signature(body, signature, secret)


def test_verify_signature_invalid():
    assert not verify_signature(b"{}", "bad", "secret")


def test_reply_text_dry_run_does_not_call_line(monkeypatch):
    monkeypatch.setattr(line_client.settings, "dry_run", True)

    def fail_post(*args, **kwargs):
        raise AssertionError("LINE API should not be called in dry run")

    monkeypatch.setattr(line_client.requests, "post", fail_post)
    line_client.reply_text("reply-token", "hello")
