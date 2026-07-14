from __future__ import annotations

from flask import Flask, redirect, request, url_for

from brain_portal.answers import (
    DeepSeekAnswerProvider,
    GeminiAnswerProvider,
    answer_query,
)
from brain_portal.auth import (
    NullMailTransport,
    create_auth_blueprint,
    create_authenticated_tenant_resolver,
    resolve_principal,
)
from brain_portal.config import PortalSettings
from brain_portal.db import PortalRepository
from brain_portal.embeddings import GeminiEmbeddingProvider
from brain_portal.models import TenantContext
from brain_portal.search import SearchResults, hybrid_search
from brain_portal.web import PortalDependencies, create_portal_blueprint


def create_app(
    settings: PortalSettings | None = None,
    dependencies: PortalDependencies | None = None,
) -> Flask:
    settings = settings or PortalSettings()
    app = Flask(__name__)
    app.config.update(
        PORTAL_DATABASE_PATH=settings.database_path,
        PORTAL_TENANT_ID=settings.tenant_id,
        PORTAL_TENANT_NAME=settings.tenant_name,
    )
    repository = PortalRepository(settings.database_path)
    mail_transport = NullMailTransport()
    app.extensions["mail_transport"] = mail_transport
    app.register_blueprint(
        create_auth_blueprint(settings, repository, mail_transport=mail_transport)
    )
    app.register_blueprint(
        create_portal_blueprint(dependencies or _default_dependencies(settings, repository))
    )

    @app.errorhandler(401)
    def redirect_unauthenticated(error):
        if settings.tenant_id.strip() or not settings.session_secret.strip():
            return error
        principal = resolve_principal(settings, repository)
        if principal is None:
            return redirect(url_for("auth.login_page", next=request.path))
        return redirect(url_for("auth.onboarding"))

    return app


def _default_dependencies(
    settings: PortalSettings, repository: PortalRepository | None = None
) -> PortalDependencies:
    repository = repository or PortalRepository(settings.database_path)
    gemini_key = settings.gemini_api_key.strip()
    deepseek_key = settings.deepseek_api_key.strip()
    embedder = (
        GeminiEmbeddingProvider(gemini_key, timeout=settings.ai_timeout_seconds)
        if gemini_key
        else None
    )
    providers = []
    if gemini_key:
        providers.append(
            GeminiAnswerProvider(
                gemini_key,
                timeout=settings.ai_timeout_seconds,
                model=settings.gemini_answer_model,
            )
        )
    if deepseek_key:
        providers.append(
            DeepSeekAnswerProvider(
                deepseek_key,
                timeout=settings.ai_timeout_seconds,
                model=settings.deepseek_answer_model,
            )
        )

    if settings.tenant_id.strip():

        def resolve_tenant() -> TenantContext | None:
            return TenantContext(settings.tenant_id, settings.tenant_name)

    else:
        resolve_tenant = create_authenticated_tenant_resolver(settings, repository)

    def search(tenant_id: str, query: str, cloud_key: str | None):
        if embedder is not None:
            return hybrid_search(
                repository,
                embedder,
                tenant_id,
                query,
                cloud_key,
            )
        hits = repository.lexical_search(
            tenant_id,
            query,
            cloud_key=cloud_key,
        )
        return SearchResults(tuple(hits), degraded=True)

    return PortalDependencies(
        repository=repository,
        tenant_resolver=resolve_tenant,
        search_service=search,
        answer_service=(
            (lambda query, hits: answer_query(query, hits, providers))
            if providers
            else (lambda query, hits: None)
        ),
    )


app = create_app()
