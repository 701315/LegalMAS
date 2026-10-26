# tests/api/test_model_configs_access.py
"""
Auth tests for model_configs endpoints (R-49).

Coverage (15 tests):
- require_superadmin guard: 3 unit tests (direct, no HTTP)
- GET list:              401 (no token), 200 (member)
- POST:                  401 (no token), 403 (member), 403 (tenant_admin),
                         422 for superadmin (proves guard passed; body empty → pydantic rejects)
- PATCH:                 401 (no token), 403 (member)
- DELETE:                401 (no token), 403 (member)
- GET usage:             401 (no token), 200 (member)

Design rationale:
- Negative (401/403) requires no DB — auth/guard fail before handler.
- Superadmin POST positive uses empty body → 422 from pydantic, which is only
  reachable if auth+guard passed. Robust: no fragile DB mocks.
- GET list / GET usage positive uses patched PlaybookRepository + mocked db.execute
  (only spot requiring DB mock — no real Test DB in project).
- DELETE success (204) not unit-tested: endpoint uses db.delete + commit directly;
  better covered by integration test (not present in project).

Pattern mirrors tests/api/test_exports_access.py (explicit override clear per test).
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.deps.auth import CurrentUser, get_current_user

# ── Test users ────────────────────────────────────────────────────────

TENANT_A = uuid.uuid4()
CONFIG_ID = uuid.uuid4()

USER_MEMBER = CurrentUser(
    id=str(uuid.uuid4()),
    global_role="member",
    tenant_id=TENANT_A,
    email="member@example.com",
)

USER_TENANT_ADMIN = CurrentUser(
    id=str(uuid.uuid4()),
    global_role="tenant_admin",
    tenant_id=TENANT_A,
    email="tenant_admin@example.com",
)

USER_SUPERADMIN = CurrentUser(
    id=str(uuid.uuid4()),
    global_role="superadmin",
    tenant_id=TENANT_A,
    email="superadmin@example.com",
)


# ── Helpers ───────────────────────────────────────────────────────────

def _override_current_user(user: CurrentUser):
    def _override():
        return user
    return _override


def _make_config_mock(cfg_id: uuid.UUID = CONFIG_ID) -> MagicMock:
    cfg = MagicMock()
    cfg.id = cfg_id
    cfg.name = "test-config"
    cfg.embeddings_primary = "intfloat/multilingual-e5-large"
    cfg.embeddings_fallback = "cointegrated/LaBSE"
    return cfg


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def app():
    from api.main import app as fastapi_app
    return fastapi_app


@pytest.fixture
def client(app):
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════
# Guard unit tests (no HTTP, no DB, no FastAPI)
# ═══════════════════════════════════════════════════════════════════════

def test_require_superadmin_accepts_superadmin():
    from api.deps.security import require_superadmin
    assert require_superadmin(USER_SUPERADMIN) is USER_SUPERADMIN


def test_require_superadmin_rejects_tenant_admin():
    from fastapi import HTTPException

    from api.deps.security import require_superadmin

    with pytest.raises(HTTPException) as exc_info:
        require_superadmin(USER_TENANT_ADMIN)
    assert exc_info.value.status_code == 403


def test_require_superadmin_rejects_member():
    from fastapi import HTTPException

    from api.deps.security import require_superadmin

    with pytest.raises(HTTPException) as exc_info:
        require_superadmin(USER_MEMBER)
    assert exc_info.value.status_code == 403


# ═══════════════════════════════════════════════════════════════════════
# GET /api/v1/model-configs
# ═══════════════════════════════════════════════════════════════════════

def test_get_list_no_token_returns_401(app, client):
    resp = client.get("/api/v1/model-configs")
    assert resp.status_code == 401


def test_get_list_member_returns_200(app, client):
    app.dependency_overrides[get_current_user] = _override_current_user(USER_MEMBER)

    with patch("api.endpoints.model_configs.PlaybookRepository") as repo_cls:
        repo = MagicMock()
        repo.list_model_configs = AsyncMock(return_value=[])
        repo_cls.return_value = repo

        resp = client.get(
            "/api/v1/model-configs",
            headers={"Authorization": "Bearer fake"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════
# POST /api/v1/model-configs
# ═══════════════════════════════════════════════════════════════════════

def test_post_no_token_returns_401(app, client):
    resp = client.post("/api/v1/model-configs", json={"name": "x"})
    assert resp.status_code == 401


def test_post_member_returns_403(app, client):
    app.dependency_overrides[get_current_user] = _override_current_user(USER_MEMBER)

    resp = client.post(
        "/api/v1/model-configs",
        json={"name": "x"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 403
    app.dependency_overrides.clear()


def test_post_tenant_admin_returns_403(app, client):
    app.dependency_overrides[get_current_user] = _override_current_user(USER_TENANT_ADMIN)

    resp = client.post(
        "/api/v1/model-configs",
        json={"name": "x"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 403
    app.dependency_overrides.clear()


def test_post_superadmin_passes_guard_422_empty_body(app, client):
    # Empty body → pydantic rejects with 422 only if auth + guard passed.
    # 401/403 would be returned earlier — so 422 proves guard accepted superadmin.
    app.dependency_overrides[get_current_user] = _override_current_user(USER_SUPERADMIN)

    resp = client.post(
        "/api/v1/model-configs",
        json={},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 422
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════
# PATCH /api/v1/model-configs/{id}
# ═══════════════════════════════════════════════════════════════════════

def test_patch_no_token_returns_401(app, client):
    resp = client.patch(f"/api/v1/model-configs/{CONFIG_ID}", json={"name": "x"})
    assert resp.status_code == 401


def test_patch_member_returns_403(app, client):
    app.dependency_overrides[get_current_user] = _override_current_user(USER_MEMBER)

    resp = client.patch(
        f"/api/v1/model-configs/{CONFIG_ID}",
        json={"name": "x"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 403
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════
# DELETE /api/v1/model-configs/{id}
# ═══════════════════════════════════════════════════════════════════════

def test_delete_no_token_returns_401(app, client):
    resp = client.delete(f"/api/v1/model-configs/{CONFIG_ID}")
    assert resp.status_code == 401


def test_delete_member_returns_403(app, client):
    app.dependency_overrides[get_current_user] = _override_current_user(USER_MEMBER)

    resp = client.delete(
        f"/api/v1/model-configs/{CONFIG_ID}",
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 403
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════
# GET /api/v1/model-configs/{id}/usage
# ═══════════════════════════════════════════════════════════════════════

def test_get_usage_no_token_returns_401(app, client):
    resp = client.get(f"/api/v1/model-configs/{CONFIG_ID}/usage")
    assert resp.status_code == 401


def test_get_usage_member_returns_200(app, client):
    from db.session import get_db

    app.dependency_overrides[get_current_user] = _override_current_user(USER_MEMBER)

    cfg = _make_config_mock()

    def _empty_result():
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        return r

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=lambda *a, **kw: _empty_result())

    async def _override_db():
        return mock_db

    app.dependency_overrides[get_db] = _override_db

    with patch("api.endpoints.model_configs.PlaybookRepository") as repo_cls:
        repo = MagicMock()
        repo.get_model_config = AsyncMock(return_value=cfg)
        repo_cls.return_value = repo

        resp = client.get(
            f"/api/v1/model-configs/{CONFIG_ID}/usage",
            headers={"Authorization": "Bearer fake"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["model_config_id"] == str(CONFIG_ID)
        assert body["playbook_versions"] == []
        assert body["deals"] == []

    app.dependency_overrides.clear()
