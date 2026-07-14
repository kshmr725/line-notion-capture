from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from flask import Blueprint, Response, redirect, render_template, request, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer

from brain_portal.config import PortalSettings
from brain_portal.db import portal_connect
from brain_portal.models import AuthenticatedPrincipal, OnboardingState, TenantContext


SESSION_COOKIE_NAME = "brain_cloud_session"
_SESSION_SALT = "brain-cloud-session"

Clock = Callable[[], datetime]
TenantResolver = Callable[[], Optional[TenantContext]]


class MailTransport:
    def send_magic_link(self, email: str, verify_url: str) -> None:
        raise NotImplementedError


class NullMailTransport(MailTransport):
    """Records messages instead of sending them. Safe default until a real
    delivery adapter (e.g. Resend SMTP) is configured for a deployment."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_magic_link(self, email: str, verify_url: str) -> None:
        self.sent.append((email, verify_url))


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


def _serializer(settings: PortalSettings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt=_SESSION_SALT)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now_iso(clock: Clock) -> str:
    return clock().isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _normalize_email(raw: str) -> str:
    return raw.strip().lower()


def create_auth_blueprint(
    settings: PortalSettings,
    repository,
    *,
    now: Clock | None = None,
    mail_transport: MailTransport | None = None,
) -> Blueprint:
    clock = now or _default_clock
    transport = mail_transport or NullMailTransport()
    auth = Blueprint("auth", __name__, template_folder="templates")

    @auth.get("/login")
    def login_page():
        return render_template("portal/login.html", page_title="登入", sent=False, invalid=False)

    @auth.post("/login/request")
    def login_request():
        email = _normalize_email(request.form.get("email", ""))
        if email and _auth_configured(settings):
            _issue_magic_link_if_invited(settings, repository, email, clock, transport)
        return render_template("portal/login.html", page_title="登入", sent=True, invalid=False)

    @auth.get("/auth/verify")
    def verify():
        token = request.args.get("token", "").strip()
        session_id = None
        if token and _auth_configured(settings):
            session_id = _consume_magic_link_token(settings, repository, token, clock)
        if session_id is None:
            return (
                render_template(
                    "portal/login.html", page_title="登入", sent=False, invalid=True
                ),
                400,
            )
        response = redirect(url_for("portal.home"))
        _set_session_cookie(response, settings, session_id)
        return response

    @auth.post("/logout")
    def logout():
        session_id = _read_session_id(settings, request)
        if session_id is not None:
            _revoke_session(repository, session_id, clock)
        response = redirect(url_for("auth.login_page"))
        response.delete_cookie(SESSION_COOKIE_NAME)
        return response

    @auth.get("/onboarding")
    def onboarding():
        principal = resolve_principal(settings, repository, clock)
        if principal is None:
            return redirect(url_for("auth.login_page"))
        state = _onboarding_state_for_user(repository, principal.user_id)
        return render_template(
            "portal/onboarding.html",
            page_title="設定 Brain Cloud",
            principal=principal,
            state=state,
            state_label=_ONBOARDING_LABELS.get(
                state.status if state else "needs_source", "準備中"
            ),
        )

    return auth


_ONBOARDING_LABELS = {
    "needs_source": "準備中",
    "proposed": "正在建立你的 Brain Cloud",
    "confirmed": "正在建立你的 Brain Cloud",
    "indexing": "正在建立你的 Brain Cloud",
    "ready": "已是最新",
}


def _auth_configured(settings: PortalSettings) -> bool:
    return bool(settings.session_secret.strip())


def _issue_magic_link_if_invited(
    settings: PortalSettings,
    repository,
    email: str,
    clock: Clock,
    transport: MailTransport,
) -> None:
    connection = portal_connect(repository.path)
    token: str | None = None
    try:
        with connection:
            invited = connection.execute(
                "SELECT 1 FROM beta_invites WHERE email = ?", (email,)
            ).fetchone()
            if invited is None:
                return
            user_id = _get_or_create_user(connection, email)
            token = secrets.token_urlsafe(32)
            connection.execute(
                """
                INSERT INTO magic_link_tokens (token_hash, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    _hash_token(token),
                    user_id,
                    _now_iso(clock),
                    (
                        clock() + timedelta(minutes=settings.magic_link_ttl_minutes)
                    ).isoformat(),
                ),
            )
    finally:
        connection.close()
    if token is not None:
        transport.send_magic_link(email, url_for("auth.verify", token=token, _external=True))


def _get_or_create_user(connection, email: str) -> str:
    row = connection.execute(
        "SELECT user_id FROM users WHERE email = ?", (email,)
    ).fetchone()
    if row is not None:
        return row["user_id"]
    user_id = secrets.token_hex(16)
    connection.execute(
        """
        INSERT INTO users (user_id, email) VALUES (?, ?)
        ON CONFLICT (email) DO NOTHING
        """,
        (user_id, email),
    )
    return connection.execute(
        "SELECT user_id FROM users WHERE email = ?", (email,)
    ).fetchone()["user_id"]


def _consume_magic_link_token(
    settings: PortalSettings, repository, token: str, clock: Clock
) -> str | None:
    token_hash = _hash_token(token)
    connection = portal_connect(repository.path)
    try:
        with connection:
            now_iso = _now_iso(clock)
            # Atomic claim: the WHERE clause folds the "unused" and
            # "not expired" checks into the same statement that marks the
            # token used, so two concurrent verifications of the same token
            # cannot both succeed (a separate SELECT-then-UPDATE would race).
            cursor = connection.execute(
                """
                UPDATE magic_link_tokens
                SET used_at = ?
                WHERE token_hash = ? AND used_at IS NULL AND expires_at >= ?
                """,
                (now_iso, token_hash, now_iso),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT user_id FROM magic_link_tokens WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            user_id = row["user_id"]
            _ensure_tenant_for_user(connection, user_id)
            session_id = secrets.token_urlsafe(32)
            connection.execute(
                """
                INSERT INTO sessions (session_id, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    _now_iso(clock),
                    (clock() + timedelta(days=settings.session_ttl_days)).isoformat(),
                ),
            )
            return session_id
    finally:
        connection.close()


def _ensure_tenant_for_user(connection, user_id: str) -> None:
    existing = connection.execute(
        "SELECT 1 FROM tenant_memberships WHERE user_id = ?", (user_id,)
    ).fetchone()
    if existing is not None:
        return
    tenant_id = user_id
    connection.execute(
        """
        INSERT INTO tenants (tenant_id, display_name)
        VALUES (?, ?)
        ON CONFLICT (tenant_id) DO NOTHING
        """,
        (tenant_id, "我的 Brain Cloud"),
    )
    connection.execute(
        """
        INSERT INTO tenant_memberships (tenant_id, user_id, role)
        VALUES (?, ?, 'owner')
        ON CONFLICT (tenant_id, user_id) DO NOTHING
        """,
        (tenant_id, user_id),
    )


def _revoke_session(repository, session_id: str, clock: Clock) -> None:
    connection = portal_connect(repository.path)
    try:
        with connection:
            connection.execute(
                "UPDATE sessions SET revoked_at = ? WHERE session_id = ?",
                (_now_iso(clock), session_id),
            )
    finally:
        connection.close()


def _onboarding_state_for_user(repository, user_id: str) -> OnboardingState | None:
    connection = portal_connect(repository.path)
    try:
        row = connection.execute(
            """
            SELECT tenant_memberships.tenant_id AS tenant_id,
                   tenants.onboarding_status AS onboarding_status
            FROM tenant_memberships
            JOIN tenants ON tenants.tenant_id = tenant_memberships.tenant_id
            WHERE tenant_memberships.user_id = ?
            ORDER BY tenant_memberships.created_at ASC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return OnboardingState(tenant_id=row["tenant_id"], status=row["onboarding_status"])


def _set_session_cookie(response: Response, settings: PortalSettings, session_id: str) -> None:
    signed = _serializer(settings).dumps(session_id)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        signed,
        max_age=settings.session_ttl_days * 24 * 3600,
        httponly=True,
        samesite="Lax",
        secure=not settings.dev_auth,
    )


def _read_session_id(settings: PortalSettings, req) -> str | None:
    if not _auth_configured(settings):
        return None
    raw = req.cookies.get(SESSION_COOKIE_NAME)
    if not raw:
        return None
    max_age = settings.session_ttl_days * 24 * 3600 + 3600
    try:
        return _serializer(settings).loads(raw, max_age=max_age)
    except BadSignature:
        return None


def resolve_principal(
    settings: PortalSettings, repository, clock: Clock | None = None
) -> AuthenticatedPrincipal | None:
    clock = clock or _default_clock
    session_id = _read_session_id(settings, request)
    if session_id is None:
        return None
    connection = portal_connect(repository.path)
    try:
        row = connection.execute(
            """
            SELECT sessions.expires_at AS expires_at,
                   sessions.revoked_at AS revoked_at,
                   users.user_id AS user_id,
                   users.email AS email
            FROM sessions
            JOIN users ON users.user_id = sessions.user_id
            WHERE sessions.session_id = ?
            """,
            (session_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None or row["revoked_at"] is not None:
        return None
    if _parse_iso(row["expires_at"]) < clock():
        return None
    return AuthenticatedPrincipal(user_id=row["user_id"], email=row["email"])


def create_authenticated_tenant_resolver(
    settings: PortalSettings, repository, clock: Clock | None = None
) -> TenantResolver:
    clock = clock or _default_clock

    def resolver() -> TenantContext | None:
        principal = resolve_principal(settings, repository, clock)
        if principal is None:
            return None
        connection = portal_connect(repository.path)
        try:
            row = connection.execute(
                """
                SELECT tenant_memberships.tenant_id AS tenant_id,
                       tenants.display_name AS display_name,
                       tenants.onboarding_status AS onboarding_status
                FROM tenant_memberships
                JOIN tenants ON tenants.tenant_id = tenant_memberships.tenant_id
                WHERE tenant_memberships.user_id = ?
                ORDER BY tenant_memberships.created_at ASC
                LIMIT 1
                """,
                (principal.user_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None or row["onboarding_status"] != "ready":
            return None
        return TenantContext(tenant_id=row["tenant_id"], display_name=row["display_name"])

    return resolver
