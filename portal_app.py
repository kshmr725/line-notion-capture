from __future__ import annotations

from flask import Flask

from brain_portal.config import PortalSettings
from brain_portal.db import PortalRepository
from brain_portal.models import TenantContext
from brain_portal.search import SearchResults
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
    app.register_blueprint(
        create_portal_blueprint(dependencies or _default_dependencies(settings))
    )
    return app


def _default_dependencies(settings: PortalSettings) -> PortalDependencies:
    repository = PortalRepository(settings.database_path)

    def resolve_tenant() -> TenantContext | None:
        if not settings.tenant_id.strip():
            return None
        return TenantContext(settings.tenant_id, settings.tenant_name)

    def lexical_search(tenant_id: str, query: str, cloud_key: str | None):
        hits = repository.lexical_search(
            tenant_id,
            query,
            cloud_key=cloud_key,
        )
        return SearchResults(tuple(hits), degraded=True)

    return PortalDependencies(
        repository=repository,
        tenant_resolver=resolve_tenant,
        search_service=lexical_search,
        answer_service=lambda query, hits: None,
    )


app = create_app()
