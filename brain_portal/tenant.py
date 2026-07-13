from flask import current_app

from brain_portal.models import TenantContext


def resolve_tenant() -> TenantContext:
    tenant_id = str(current_app.config.get("PORTAL_TENANT_ID") or "").strip()
    if not tenant_id:
        raise PermissionError("tenant context is required")
    return TenantContext(
        tenant_id=tenant_id,
        display_name=str(current_app.config.get("PORTAL_TENANT_NAME") or tenant_id),
    )
