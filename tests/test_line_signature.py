import base64
import hashlib
import hmac

from line_client import verify_signature


def test_verify_signature_valid():
    body = b'{"events":[]}'
    secret = "test-secret"
    signature = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    assert verify_signature(body, signature, secret)


def test_verify_signature_invalid():
    assert not verify_signature(b"{}", "bad", "secret")
