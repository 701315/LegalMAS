# tests/api/test_exports_access.py

"""
Тесты tenant-isolation и project-level RBAC для export endpoints.

Сценарии:
1. Без токена → 401
2. Cross-tenant access → 404
3. Same-tenant, no project membership → 403
4. Same-tenant, viewer membership → 200
5. Same-tenant, editor membership → 200
6. Same-tenant, tenant_admin (без membership) → 200
7. Superadmin (другой tenant, без membership) → 200
8. Cross-tenant download → 404
9. Same-tenant viewer download (not completed) → 409
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.deps.auth import CurrentUser


# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()
DEAL_A = uuid.uuid4()
RUN_A = uuid.uuid4()
EXPORT_A = uuid.uuid4()

USER_TENANT_A_MEMBER = CurrentUser(
    id=str(uuid.uuid4()),
    global_role="member",
    tenant_id=TENANT_A,
    email="member_a@example.com",
)

USER_TENANT_A_VIEWER = CurrentUser(
    id=str(uuid.uuid4()),
    global_role="member",
    tenant_id=TENANT_A,
    email="viewer_a@example.com",
)

USER_TENANT_A_EDITOR = CurrentUser(
    id=str(uuid.uuid4()),
    global_role="member",
    tenant_id=TENANT_A,
    email="editor_a@example.com",
)

USER_TENANT_A_ADMIN = CurrentUser(
    id=str(uuid.uuid4()),
    global_role="tenant_admin",
    tenant_id=TENANT_A,
    email="admin_a@example.com",
)

USER_TENANT_B_MEMBER = CurrentUser(
    id=str(uuid.uuid4()),
    global_role="member",
    tenant_id=TENANT_B,
    email="member_b@example.com",
)

USER_SUPERADMIN = CurrentUser(
    id=str(uuid.uuid4()),
    global_role="superadmin",
    tenant_id=TENANT_B,  # superadmin может быть из другого tenant
    email="superadmin@example.com",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_export(
    export_id: uuid.UUID = EXPORT_A,
    deal_id: uuid.UUID = DEAL_A,
    run_id: uuid.UUID = RUN_A,
    status: str = "completed",
    file_ref: str = "exports/test.xlsx",
    export_type: str = "grid_xlsx",
    file_size_bytes: int = 1024,
) -> Any:
    """
    Простой fake object вместо ORM Export.
    """

    class FakeExport:
        pass

    export = FakeExport()
    export.id = export_id
    export.deal_id = deal_id
    export.run_id = run_id
    export.export_type = export_type
    export.file_ref = file_ref
    export.file_refs = None
    export.requested_by = "test@example.com"
    export.requester_role = "deal_owner"
    export.file_size_bytes = file_size_bytes
    export.status = status
    export.error_message = None
    export.created_at = datetime.now(timezone.utc)
    export.updated_at = datetime.now(timezone.utc)
    return export


def _override_current_user(user: CurrentUser):
    """
    FastAPI dependency override для get_current_user.
    """
    def _override():
        return user
    return _override


def _build_scoped_export_mock(
    export: Any,
    deal_tenant_id: uuid.UUID,
):
    """
    Mock для _get_scoped_export_or_404().

    Поведение:
    - superadmin видит всё
    - same-tenant user видит export
    - cross-tenant user получает 404
    """
    async def _mock(db, export_id, user):
        from fastapi import HTTPException, status

        if user.global_role == "superadmin":
            return export

        if user.tenant_id == deal_tenant_id:
            return export

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export not found",
        )

    return _mock


def _build_require_project_role_mock(
    *,
    deal_tenant_id: uuid.UUID,
    allowed_user_ids: set[str] | None = None,
):
    """
    Mock для require_project_role().

    Поведение:
    - superadmin → pass
    - tenant_admin своего tenant → pass
    - member из allowed_user_ids → pass
    - иначе → 403
    """
    async def _mock(db, user, deal_id, allowed_roles):
        from fastapi import HTTPException

        if user.global_role == "superadmin":
            return

        if user.global_role == "tenant_admin" and user.tenant_id == deal_tenant_id:
            return

        if allowed_user_ids and user.id in allowed_user_ids:
            return

        raise HTTPException(status_code=403, detail="Insufficient project role")

    return _mock


@pytest.fixture
def app():
    from api.main import app as fastapi_app
    return fastapi_app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def fake_export():
    return _make_fake_export()


@pytest.fixture
def fake_export_pending():
    return _make_fake_export(
        status="pending",
        file_ref="",
    )


# ---------------------------------------------------------------------------
# Status endpoint tests
# ---------------------------------------------------------------------------

def test_export_status_without_auth_returns_401(client):
    resp = client.get(f"/api/v1/exports/{EXPORT_A}")
    assert resp.status_code == 401


def test_export_status_cross_tenant_returns_404(app, client, fake_export):
    from api.deps.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_current_user(USER_TENANT_B_MEMBER)

    scoped_mock = _build_scoped_export_mock(fake_export, TENANT_A)

    with patch(
        "api.endpoints.exports._get_scoped_export_or_404",
        new=scoped_mock,
    ):
        resp = client.get(
            f"/api/v1/exports/{EXPORT_A}",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 404

    app.dependency_overrides.clear()


def test_export_status_same_tenant_no_membership_returns_403(app, client, fake_export):
    from api.deps.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_current_user(USER_TENANT_A_MEMBER)

    scoped_mock = _build_scoped_export_mock(fake_export, TENANT_A)
    role_mock = _build_require_project_role_mock(
        deal_tenant_id=TENANT_A,
        allowed_user_ids=set(),
    )

    with (
        patch("api.endpoints.exports._get_scoped_export_or_404", new=scoped_mock),
        patch("api.endpoints.exports.require_project_role", new=role_mock),
    ):
        resp = client.get(
            f"/api/v1/exports/{EXPORT_A}",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 403

    app.dependency_overrides.clear()


def test_export_status_same_tenant_viewer_returns_200(app, client, fake_export):
    from api.deps.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_current_user(USER_TENANT_A_VIEWER)

    scoped_mock = _build_scoped_export_mock(fake_export, TENANT_A)
    role_mock = _build_require_project_role_mock(
        deal_tenant_id=TENANT_A,
        allowed_user_ids={USER_TENANT_A_VIEWER.id},
    )

    with (
        patch("api.endpoints.exports._get_scoped_export_or_404", new=scoped_mock),
        patch("api.endpoints.exports.require_project_role", new=role_mock),
    ):
        resp = client.get(
            f"/api/v1/exports/{EXPORT_A}",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(EXPORT_A)
        assert data["status"] == "completed"

    app.dependency_overrides.clear()


def test_export_status_same_tenant_editor_returns_200(app, client, fake_export):
    from api.deps.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_current_user(USER_TENANT_A_EDITOR)

    scoped_mock = _build_scoped_export_mock(fake_export, TENANT_A)
    role_mock = _build_require_project_role_mock(
        deal_tenant_id=TENANT_A,
        allowed_user_ids={USER_TENANT_A_EDITOR.id},
    )

    with (
        patch("api.endpoints.exports._get_scoped_export_or_404", new=scoped_mock),
        patch("api.endpoints.exports.require_project_role", new=role_mock),
    ):
        resp = client.get(
            f"/api/v1/exports/{EXPORT_A}",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 200

    app.dependency_overrides.clear()


def test_export_status_tenant_admin_without_membership_returns_200(app, client, fake_export):
    from api.deps.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_current_user(USER_TENANT_A_ADMIN)

    scoped_mock = _build_scoped_export_mock(fake_export, TENANT_A)
    role_mock = _build_require_project_role_mock(
        deal_tenant_id=TENANT_A,
    )

    with (
        patch("api.endpoints.exports._get_scoped_export_or_404", new=scoped_mock),
        patch("api.endpoints.exports.require_project_role", new=role_mock),
    ):
        resp = client.get(
            f"/api/v1/exports/{EXPORT_A}",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 200

    app.dependency_overrides.clear()


def test_export_status_superadmin_cross_tenant_returns_200(app, client, fake_export):
    from api.deps.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_current_user(USER_SUPERADMIN)

    scoped_mock = _build_scoped_export_mock(fake_export, TENANT_A)
    role_mock = _build_require_project_role_mock(
        deal_tenant_id=TENANT_A,
    )

    with (
        patch("api.endpoints.exports._get_scoped_export_or_404", new=scoped_mock),
        patch("api.endpoints.exports.require_project_role", new=role_mock),
    ):
        resp = client.get(
            f"/api/v1/exports/{EXPORT_A}",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 200

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Download endpoint tests
# ---------------------------------------------------------------------------

def test_export_download_without_auth_returns_401(client):
    resp = client.get(f"/api/v1/exports/{EXPORT_A}/download")
    assert resp.status_code == 401


def test_export_download_cross_tenant_returns_404(app, client, fake_export):
    from api.deps.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_current_user(USER_TENANT_B_MEMBER)

    scoped_mock = _build_scoped_export_mock(fake_export, TENANT_A)

    with patch(
        "api.endpoints.exports._get_scoped_export_or_404",
        new=scoped_mock,
    ):
        resp = client.get(
            f"/api/v1/exports/{EXPORT_A}/download",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 404

    app.dependency_overrides.clear()


def test_export_download_same_tenant_no_membership_returns_403(app, client, fake_export):
    from api.deps.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_current_user(USER_TENANT_A_MEMBER)

    scoped_mock = _build_scoped_export_mock(fake_export, TENANT_A)
    role_mock = _build_require_project_role_mock(
        deal_tenant_id=TENANT_A,
        allowed_user_ids=set(),
    )

    with (
        patch("api.endpoints.exports._get_scoped_export_or_404", new=scoped_mock),
        patch("api.endpoints.exports.require_project_role", new=role_mock),
    ):
        resp = client.get(
            f"/api/v1/exports/{EXPORT_A}/download",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 403

    app.dependency_overrides.clear()


def test_export_download_pending_export_returns_409(app, client, fake_export_pending):
    from api.deps.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_current_user(USER_TENANT_A_VIEWER)

    scoped_mock = _build_scoped_export_mock(fake_export_pending, TENANT_A)
    role_mock = _build_require_project_role_mock(
        deal_tenant_id=TENANT_A,
        allowed_user_ids={USER_TENANT_A_VIEWER.id},
    )

    with (
        patch("api.endpoints.exports._get_scoped_export_or_404", new=scoped_mock),
        patch("api.endpoints.exports.require_project_role", new=role_mock),
    ):
        resp = client.get(
            f"/api/v1/exports/{EXPORT_A}/download",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 409

    app.dependency_overrides.clear()


    