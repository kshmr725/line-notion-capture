from __future__ import annotations

from email.message import EmailMessage

import pytest

import portal_app
import brain_portal.auth as auth
from brain_portal.config import PortalSettings


class RecordingSmtp:
    def __init__(self, host: str, port: int, timeout: float):
        self.connection = (host, port, timeout)
        self.started_tls = False
        self.login_args = None
        self.messages: list[EmailMessage] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, username: str, password: str):
        self.login_args = (username, password)

    def send_message(self, message: EmailMessage):
        self.messages.append(message)


def _smtp_settings(**overrides) -> PortalSettings:
    values = {
        "session_secret": "production-session-secret",
        "dev_auth": False,
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "mailer",
        "smtp_password": "smtp-secret",
        "smtp_from_email": "Brain Cloud <login@example.com>",
        "smtp_use_tls": True,
    }
    values.update(overrides)
    return PortalSettings(**values)


def test_smtp_transport_sends_a_plain_text_magic_link_without_logging_it():
    smtp = None

    def factory(host: str, port: int, timeout: float):
        nonlocal smtp
        smtp = RecordingSmtp(host, port, timeout)
        return smtp

    transport = auth.SmtpMailTransport(_smtp_settings(), smtp_factory=factory)

    transport.send_magic_link(
        "reader@example.com", "https://brain.example.com/auth/verify?token=sensitive"
    )

    assert smtp is not None
    assert smtp.connection == ("smtp.example.com", 587, 20.0)
    assert smtp.started_tls is True
    assert smtp.login_args == ("mailer", "smtp-secret")
    assert len(smtp.messages) == 1
    message = smtp.messages[0]
    assert message["To"] == "reader@example.com"
    assert message["From"] == "Brain Cloud <login@example.com>"
    assert message["Subject"] == "登入 Brain Cloud"
    assert "https://brain.example.com/auth/verify?token=sensitive" in message.get_content()


def test_production_multi_tenant_app_fails_closed_without_mail_configuration(tmp_path):
    settings = PortalSettings(
        database_path=str(tmp_path / "portal.sqlite3"),
        tenant_id="",
        session_secret="production-session-secret",
        dev_auth=False,
    )

    with pytest.raises(RuntimeError, match="SMTP"):
        portal_app.create_app(settings=settings)


def test_development_auth_keeps_the_deterministic_mail_adapter():
    transport = auth.build_mail_transport(
        PortalSettings(session_secret="test-secret", dev_auth=True)
    )

    assert isinstance(transport, auth.NullMailTransport)


def test_production_mail_requires_an_smtp_username():
    with pytest.raises(RuntimeError, match="PORTAL_SMTP_USERNAME"):
        auth.build_mail_transport(_smtp_settings(smtp_username=""))
