import pytest
from flask import Flask

from brain_portal.tenant import resolve_tenant


def test_tenant_comes_from_server_config_not_query_string():
    app = Flask(__name__)
    app.config.update(PORTAL_TENANT_ID="kevin", TESTING=False)
    with app.test_request_context("/?tenant_id=attacker"):
        assert resolve_tenant().tenant_id == "kevin"


def test_missing_tenant_is_rejected():
    app = Flask(__name__)
    with app.test_request_context("/"):
        with pytest.raises(PermissionError):
            resolve_tenant()
